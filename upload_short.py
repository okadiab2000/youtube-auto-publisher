
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

BASE = Path(__file__).resolve().parent
QUEUE_FILE = BASE / "queue.json"
TITLES_FILE = BASE / "titles.txt"
STATE_FILE = BASE / "state.json"

FOLDER_ID = os.environ.get(
    "DRIVE_FOLDER_ID",
    "1iiUPSTGe0SVsCkjofChkEW4MaceIhXSY",
)

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]

CAIRO = ZoneInfo("Africa/Cairo")
ALLOWED_HOURS = {15, 20}


def load_json(path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {path.name}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_state(state):
    temp_file = STATE_FILE.with_suffix(".tmp")

    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")

    temp_file.replace(STATE_FILE)


def get_credentials():
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")

    if token_json:
        creds = Credentials.from_authorized_user_info(
            json.loads(token_json),
            SCOPES,
        )
    else:
        creds = Credentials.from_authorized_user_file(
            str(BASE / "token.json"),
            SCOPES,
        )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        if not token_json:
            (BASE / "token.json").write_text(
                creds.to_json(),
                encoding="utf-8",
            )

    if not creds.valid:
        raise RuntimeError(
            "Google authentication failed. Check token.json "
            "or the GOOGLE_TOKEN_JSON GitHub secret."
        )

    return creds


def get_drive_videos(drive):
    result = []
    page_token = None

    while True:
        response = drive.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed = false",
            pageSize=1000,
            pageToken=page_token,
            orderBy="name",
            fields="nextPageToken,files(id,name,mimeType)",
        ).execute()

        result.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return [
        item for item in result
        if item.get("mimeType", "").startswith("video/")
    ]


def match_queue(queue_data, drive_videos):
    if isinstance(queue_data, dict):
        queue_data = queue_data.get(
            "videos",
            queue_data.get("queue", []),
        )

    if not isinstance(queue_data, list) or not queue_data:
        raise RuntimeError(
            "queue.json is empty or has an unexpected format."
        )

    drive_by_name = {}

    for video in drive_videos:
        name = video["name"]

        if name in drive_by_name:
            raise RuntimeError(f"Duplicate filename in Drive: {name}")

        drive_by_name[name] = video

    matched = []
    missing = []

    for entry in queue_data:
        name = entry.get("filename")

        if not name and entry.get("relative_path"):
            name = Path(entry["relative_path"]).name

        if not name:
            raise RuntimeError(
                "A queue.json entry has no filename."
            )

        item = drive_by_name.get(name)

        if not item:
            missing.append(name)
        else:
            matched.append({
                "name": name,
                "drive_id": item["id"],
            })

    if missing:
        raise RuntimeError(
            f"{len(missing)} filenames from queue.json were not found "
            "in the Drive folder. No upload was attempted.\n"
            + "\n".join(missing[:10])
        )

    return matched


def get_titles():
    if not TITLES_FILE.exists():
        raise FileNotFoundError("Create titles.txt first.")

    titles = [
        line.strip()
        for line in TITLES_FILE.read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if line.strip()
    ]

    if not titles:
        raise RuntimeError("titles.txt contains no titles.")

    if any(len(title) > 100 for title in titles):
        raise RuntimeError(
            "Every YouTube title must be 100 characters or less."
        )

    return titles


def download_video(drive, video):
    suffix = Path(video["name"]).suffix or ".webm"

    temp = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=suffix,
    )
    temp_path = temp.name

    try:
        request = drive.files().get_media(
            fileId=video["drive_id"]
        )
        downloader = MediaIoBaseDownload(temp, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

            if status:
                print(
                    f"Download: {int(status.progress() * 100)}%"
                )

        temp.close()
        return temp_path

    except Exception:
        temp.close()
        Path(temp_path).unlink(missing_ok=True)
        raise


def publish_video(youtube, path, title):
    description = os.environ.get(
        "YOUTUBE_DESCRIPTION",
        "استمع و ارح قلبك 🤍\n#shorts #قرآن_كريم",
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title,
                "description": description,
                "tags": [
                    "shorts",
                    "قرآن_كريم",
                    "تلاوة_خاشعة",
                ],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=MediaFileUpload(
            path,
            mimetype="video/*",
            chunksize=8 * 1024 * 1024,
            resumable=True,
        ),
    )

    response = None

    while response is None:
        status, response = request.next_chunk()

        if status:
            print(f"Upload: {int(status.progress() * 100)}%")

    return response["id"]



def main():
    mode = "dry-run"

    if "--prepare" in sys.argv:
        mode = "prepare"
    elif "--publish" in sys.argv:
        mode = "publish"

    if FOLDER_ID == "PUT_FOLDER_ID_HERE":
        raise RuntimeError("Set DRIVE_FOLDER_ID to your actual Drive folder ID.")

    now = datetime.now(CAIRO)
    slot = now.strftime("%Y-%m-%d-%H")

    state = load_json(
        STATE_FILE,
        {
            "next_video_index": 0,
            "next_title_index": 0,
            "published": [],
            "processed_slots": [],
            "pending_upload": None,
        },
    )

    state.setdefault("next_video_index", 0)
    state.setdefault("next_title_index", 0)
    state.setdefault("published", [])
    state.setdefault("processed_slots", [])
    state.setdefault("pending_upload", None)

    if mode == "publish":
        pending = state["pending_upload"]

        if pending is None:
            raise RuntimeError("No prepared upload exists. Nothing published.")

        creds = get_credentials()
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        video = {
            "name": pending["filename"],
            "drive_id": pending["drive_file_id"],
        }

        path = None

        try:
            path = download_video(drive, video)
            youtube_id = publish_video(youtube, path, pending["title"])

            state["published"].append({
                "filename": pending["filename"],
                "drive_file_id": pending["drive_file_id"],
                "youtube_video_id": youtube_id,
                "title": pending["title"],
                "published_at": datetime.now(CAIRO).isoformat(),
                "slot": pending["slot"],
            })

            state["next_video_index"] = pending["video_index"] + 1
            state["next_title_index"] = (
                pending["title_index"] + 1
            ) % len(get_titles())

            state["processed_slots"].append(pending["slot"])
            state["processed_slots"] = state["processed_slots"][-90:]
            state["pending_upload"] = None

            save_state(state)

            print(f"Published successfully: https://youtu.be/{youtube_id}")

        finally:
            if path and os.path.exists(path):
                os.remove(path)

        return

    if state["pending_upload"] is not None:
        raise RuntimeError(
            "A previous upload is unresolved. "
            "Check YouTube and reconcile state.json before retrying."
        )

    if mode == "prepare" and now.hour not in ALLOWED_HOURS:
        print(f"Cairo time: {now:%Y-%m-%d %H:%M}")
        print("Outside the scheduled publishing hours. Nothing prepared.")
        return

    if mode == "prepare" and slot in state["processed_slots"]:
        print(f"Slot {slot} already processed. Nothing prepared.")
        return

    titles = get_titles()
    queue_data = load_json(QUEUE_FILE)

    creds = get_credentials()
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)

    drive_videos = get_drive_videos(drive)
    queue = match_queue(queue_data, drive_videos)

    video_index = state["next_video_index"]
    title_index = state["next_title_index"]

    if video_index >= len(queue):
        print("All videos in the queue have been processed.")
        return

    if title_index >= len(titles):
        raise RuntimeError("next_title_index is outside the available titles.")

    video = queue[video_index]
    title = titles[title_index]

    print(f"Cairo time: {now:%Y-%m-%d %H:%M:%S}")
    print(f"Drive videos: {len(drive_videos)}")
    print(f"Next video: {video_index + 1}/{len(queue)}")
    print(f"Filename: {video['name']}")
    print(f"Title: {title}")

    if mode == "dry-run":
        print("DRY RUN: no video was published.")
        return

    state["pending_upload"] = {
        "filename": video["name"],
        "drive_file_id": video["drive_id"],
        "title": title,
        "slot": slot,
        "video_index": video_index,
        "title_index": title_index,
        "started_at": datetime.now(CAIRO).isoformat(),
    }

    save_state(state)
    print("Upload prepared. Persist state.json before uploading.")


if __name__ == "__main__":
    main()
