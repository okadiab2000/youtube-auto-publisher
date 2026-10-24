
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import date, datetime
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
from google.auth.transport.requests import Request


# =========================================================
# SETTINGS
# =========================================================

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
START_DATE = date(2026, 10, 19)

# Grace window around each allowed hour so delayed (or slightly early)
# GitHub Actions runs still map to the correct Cairo slot.
# Window for hour H: from (H-1):50 until (H+1):25 Cairo time.
EARLY_MINUTES = 10   # accept runs starting 10 minutes before the hour
LATE_MINUTES = 85    # accept runs up to 1h25m after the hour starts

VIDEO_DESCRIPTION = os.environ.get(
    "VIDEO_DESCRIPTION",
    "استمع وريح قلبك ❤️\n"
    "#shorts #القرآن_الكريم #اكسبلور_فولو",
)


# =========================================================
# GENERAL HELPERS
# =========================================================

def now_cairo():
    return datetime.now(CAIRO)


def resolve_publish_slot(now=None):
    """
    Return the Cairo slot key (YYYY-MM-DD-HH) that is currently open for
    publishing, or None if we are outside every allowed window.

    Each allowed hour H has a window of roughly:
        (H-1):50  →  (H+1):25   (Cairo local time)

    This absorbs typical GitHub Actions cron jitter (early or late) without
    ever opening a non-allowed hour as a new slot.
    """
    from datetime import timedelta

    now = now or now_cairo()

    if now.date() < START_DATE:
        return None

    candidates = []
    for hour in sorted(ALLOWED_HOURS):
        try:
            slot_start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        except ValueError:
            continue

        window_open = slot_start - timedelta(minutes=EARLY_MINUTES)
        window_close = slot_start + timedelta(minutes=LATE_MINUTES)

        if window_open <= now < window_close:
            candidates.append((abs((now - slot_start).total_seconds()), hour, slot_start.date()))

    if not candidates:
        return None

    # Prefer the closest nominal hour (handles rare overlapping windows)
    _, hour, slot_date = min(candidates, key=lambda x: x[0])
    return f"{slot_date:%Y-%m-%d}-{hour}"


def check_schedule(now=None):
    """Raise if the current Cairo time is outside any allowed publish window."""
    now = now or now_cairo()

    if now.date() < START_DATE:
        raise RuntimeError(
            f"Publishing starts on {START_DATE}. Current Cairo date: {now.date()}"
        )

    slot = resolve_publish_slot(now)
    if slot is None:
        raise RuntimeError(
            f"Publishing is allowed only near hours {sorted(ALLOWED_HOURS)} "
            f"Cairo time (with a short grace window). "
            f"Current time: {now:%Y-%m-%d %H:%M:%S}"
        )


def load_json(path, default=None):
    if not path.exists():
        if default is not None:
            return default
        raise FileNotFoundError(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json_atomic(path, data):
    """Write JSON atomically to reduce the risk of a damaged state file."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        prefix=f"{path.stem}_",
        suffix=".tmp",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, path)

    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def save_state(state):
    save_json_atomic(STATE_FILE, state)


def current_slot(now=None):
    """
    Return the active publish slot for the current moment.
    Falls back to the strict hour-based key only when no grace window matches
    (should not happen when check_schedule has already passed).
    """
    now = now or now_cairo()
    resolved = resolve_publish_slot(now)
    if resolved is not None:
        return resolved
    return f"{now:%Y-%m-%d}-{now.hour}"


def write_github_output(key, value):
    """Write an output only when running inside GitHub Actions."""
    output_path = os.environ.get("GITHUB_OUTPUT")

    if output_path:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")


# =========================================================
# GOOGLE AUTHENTICATION
# =========================================================

def get_credentials():
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")

    if not token_json:
        raise RuntimeError(
            "Missing GOOGLE_TOKEN_JSON environment variable."
        )

    try:
        token_info = json.loads(token_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GOOGLE_TOKEN_JSON is not valid JSON."
        ) from exc

    credentials = Credentials.from_authorized_user_info(
        token_info,
        SCOPES,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials.valid:
        raise RuntimeError(
            "Google credentials are invalid or expired. "
            "Refresh the Google authorization before publishing."
        )

    return credentials


def get_google_services():
    credentials = get_credentials()

    drive = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    return drive, youtube


# =========================================================
# GOOGLE DRIVE / QUEUE
# =========================================================

def get_drive_videos(drive):
    """List video files directly inside the configured Drive folder."""
    files = []
    page_token = None

    while True:
        response = drive.files().list(
            q=(
                f"'{FOLDER_ID}' in parents "
                "and trashed = false "
                "and mimeType contains 'video/'"
            ),
            pageSize=1000,
            orderBy="modifiedTime",
            pageToken=page_token,
            fields="nextPageToken, files(id, name, mimeType, size, modifiedTime)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()

        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return files


def queue_entries(queue_data):
    """Support either a JSON list or an object containing videos/queue."""
    if isinstance(queue_data, list):
        return queue_data

    if isinstance(queue_data, dict):
        for key in ("videos", "queue"):
            value = queue_data.get(key)
            if isinstance(value, list):
                return value

    raise ValueError(
        "Unsupported queue.json format. Expected a list or an object "
        "containing a 'videos' or 'queue' list."
    )


def item_drive_id(item):
    if not isinstance(item, dict):
        return None

    for key in ("id", "drive_file_id", "file_id"):
        value = item.get(key)
        if value:
            return str(value)

    return None


def item_filename(item):
    if not isinstance(item, dict):
        return None

    for key in ("filename", "name", "relative_path"):
        value = item.get(key)
        if value:
            return str(value)

    return None


def sync_queue(drive):
    """
    Refresh queue.json from Drive while retaining existing order where possible.
    Existing entries are matched by Drive file ID first, then filename.
    """
    if QUEUE_FILE.exists():
        original_data = load_json(QUEUE_FILE)
        existing = queue_entries(original_data)
    else:
        original_data = {"videos": []}
        existing = []

    drive_files = get_drive_videos(drive)

    existing_by_id = {}
    existing_by_name = {}

    for item in existing:
        file_id = item_drive_id(item)
        filename = item_filename(item)

        if file_id:
            existing_by_id[file_id] = item

        if filename:
            existing_by_name[filename] = item

    refreshed = []
    seen_ids = set()

    # Keep the existing queue order for items still present in Drive.
    for item in existing:
        file_id = item_drive_id(item)
        filename = item_filename(item)

        match = None

        if file_id:
            match = next(
                (f for f in drive_files if f.get("id") == file_id),
                None,
            )

        if match is None and filename:
            match = next(
                (f for f in drive_files if f.get("name") == filename),
                None,
            )

        if match is None:
            continue

        if match["id"] in seen_ids:
            continue

        refreshed.append({
            "id": match["id"],
            "filename": match["name"],
        })
        seen_ids.add(match["id"])

    # Append newly discovered videos in oldest-modified-first order.
    # Existing queue entries retain their established order.
    new_drive_files = sorted(
        drive_files,
        key=lambda item: item.get("modifiedTime", ""),
    )
    for item in new_drive_files:
        file_id = item.get("id")

        if not file_id or file_id in seen_ids:
            continue

        refreshed.append({
            "id": file_id,
            "filename": item["name"],
        })
        seen_ids.add(file_id)

    if isinstance(original_data, dict):
        if "videos" in original_data:
            original_data["videos"] = refreshed
        elif "queue" in original_data:
            original_data["queue"] = refreshed
        else:
            original_data = {"videos": refreshed}
    else:
        original_data = {"videos": refreshed}

    save_json_atomic(QUEUE_FILE, original_data)

    print(f"Queue synced: {len(refreshed)} videos.")
    return refreshed


# =========================================================
# TITLES
# =========================================================

def get_titles():
    if not TITLES_FILE.exists():
        raise FileNotFoundError(f"Missing titles file: {TITLES_FILE}")

    with TITLES_FILE.open("r", encoding="utf-8-sig") as f:
        titles = [
            line.strip()
            for line in f
            if line.strip()
        ]

    if not titles:
        raise RuntimeError("titles.txt contains no titles.")

    return titles


# =========================================================
# VIDEO DOWNLOAD
# =========================================================

def download_video(drive, drive_file_id, filename):
    """Download a Drive video into a temporary local file."""
    suffix = Path(filename).suffix or ".mp4"

    fd, local_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)

    try:
        request = drive.files().get_media(
            fileId=drive_file_id,
            supportsAllDrives=True,
        )

        with open(local_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False

            while not done:
                status, done = downloader.next_chunk()

                if status:
                    print(
                        f"Download progress: {int(status.progress() * 100)}%"
                    )

        if os.path.getsize(local_path) == 0:
            raise RuntimeError("Downloaded video is empty.")

        print(
            f"Downloaded {filename} "
            f"({os.path.getsize(local_path)} bytes)."
        )

        return local_path

    except Exception:
        try:
            os.remove(local_path)
        except OSError:
            pass
        raise


# =========================================================
# YOUTUBE UPLOAD
# =========================================================

def publish_video(youtube, local_path, title):
    """
    Upload a video publicly to YouTube.

    IMPORTANT:
    If the request fails after YouTube has accepted it, the outcome may be
    uncertain. The caller must not automatically retry that upload.
    """
    body = {
        "snippet": {
            "title": title[:100],
            "description": VIDEO_DESCRIPTION,
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        local_path,
        mimetype="video/*",
        resumable=True,
        chunksize=8 * 1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None

    while response is None:
        status, response = request.next_chunk()

        if status:
            print(
                f"YouTube upload progress: "
                f"{int(status.progress() * 100)}%"
            )

    video_id = response.get("id")

    if not video_id:
        raise RuntimeError(
            "YouTube upload returned no video ID. "
            "Treat the result as unresolved and check YouTube manually."
        )

    print(f"Published successfully: https://youtu.be/{video_id}")
    return video_id


# =========================================================
# SCHEDULE CHECK
# =========================================================

def cmd_check_slot():
    now = now_cairo()
    slot = resolve_publish_slot(now)
    allowed = slot is not None

    write_github_output(
        "allowed",
        "true" if allowed else "false",
    )
    if allowed:
        write_github_output("slot", slot)

    print(f"Cairo time: {now:%Y-%m-%d %H:%M:%S}")
    print(f"Start date: {START_DATE}")
    print(f"Allowed hours: {sorted(ALLOWED_HOURS)}")
    print(f"Grace window: -{EARLY_MINUTES}m / +{LATE_MINUTES}m around each hour")
    print(f"Resolved slot: {slot}")
    print(f"Publishing allowed: {allowed}")


# =========================================================
# PREPARE NEXT VIDEO
# =========================================================

def cmd_prepare():
    check_schedule()

    state = load_json(STATE_FILE, default={
        "next_video_index": 0,
        "next_title_index": 0,
        "published": [],
        "processed_slots": [],
        "pending_upload": None,
    })

    if state.get("pending_upload") is not None:
        raise RuntimeError(
            "A previous upload is unresolved. "
            "Check YouTube and reconcile state.json before preparing another."
        )

    slot = current_slot()

    if slot in state.get("processed_slots", []):
        print(f"Slot {slot} was already processed. Nothing to prepare.")
        return

    titles = get_titles()
    video_index = int(state.get("next_video_index", 0))
    title_index = int(state.get("next_title_index", 0))

    if title_index < 0:
        raise RuntimeError(f"Invalid next_title_index={title_index}.")

    # Stop before contacting Google APIs when all configured titles are used.
    if title_index >= len(titles):
        print(
            f"TITLE_EXHAUSTED: all {len(titles)} titles have been used. "
            "No upload will be prepared."
        )
        write_github_output("ready", "false")
        return

    drive, _ = get_google_services()
    videos = sync_queue(drive)

    if not videos:
        raise RuntimeError(
            "No videos were found in the configured Google Drive folder."
        )

    if video_index < 0 or video_index >= len(videos):
        raise RuntimeError(
            f"next_video_index={video_index} is outside the queue "
            f"of {len(videos)} videos."
        )

    video = videos[video_index]
    drive_id = item_drive_id(video)
    filename = item_filename(video)

    if not drive_id or not filename:
        raise RuntimeError(
            f"Invalid queue entry at index {video_index}: {video!r}"
        )

    title = titles[title_index]

    state["pending_upload"] = {
        "filename": filename,
        "drive_file_id": drive_id,
        "title": title,
        "slot": slot,
        "video_index": video_index,
        "title_index": title_index,
        "started_at": now_cairo().isoformat(),
        "status": "prepared",
    }

    save_state(state)

    print("Next video prepared.")
    print(f"Filename: {filename}")
    print(f"Title: {title}")
    print(f"Slot: {slot}")
    print("Status: prepared")


# =========================================================
# LOCK BEFORE UPLOAD
# =========================================================

def cmd_lock():
    state = load_json(STATE_FILE)
    pending = state.get("pending_upload")

    if pending is None:
        print("No prepared upload. Nothing to lock.")
        write_github_output("attempt", "false")
        return

    status = pending.get("status", "prepared")

    # Never automatically retry an upload with an uncertain outcome.
    if status == "uploading":
        print(
            "Upload outcome is unresolved. Automatic retry blocked. "
            "Check YouTube and reconcile state.json manually."
        )
        write_github_output("attempt", "false")
        return

    if status != "prepared":
        print(
            f"Unexpected pending status: {status!r}. "
            "Automatic upload blocked."
        )
        write_github_output("attempt", "false")
        return

    pending["status"] = "uploading"
    pending["locked_at"] = now_cairo().isoformat()

    save_state(state)

    print("Upload locked. One upload attempt authorized.")
    write_github_output("attempt", "true")


# =========================================================
# PUBLISH PREPARED VIDEO
# =========================================================

def cmd_publish():
    check_schedule()

    state = load_json(STATE_FILE)
    pending = state.get("pending_upload")

    if pending is None:
        raise RuntimeError(
            "No prepared upload exists. Nothing published."
        )

    if pending.get("status") != "uploading":
        raise RuntimeError(
            "Upload is not locked. Nothing published."
        )

    drive_id = pending.get("drive_file_id")
    filename = pending.get("filename")
    title = pending.get("title")
    slot = pending.get("slot")

    if not all((drive_id, filename, title, slot)):
        raise RuntimeError(
            "Pending upload is missing required fields. "
            "Nothing published."
        )

    if slot in state.get("processed_slots", []):
        raise RuntimeError(
            f"Slot {slot} is already marked processed. "
            "Refusing to publish again."
        )

    drive, youtube = get_google_services()
    local_path = None

    try:
        local_path = download_video(
            drive,
            drive_id,
            filename,
        )

        video_id = publish_video(
            youtube,
            local_path,
            title,
        )

        # Update state only after receiving a YouTube video ID.
        published_item = {
            "filename": filename,
            "drive_file_id": drive_id,
            "youtube_video_id": video_id,
            "title": title,
            "published_at": now_cairo().isoformat(),
            "slot": slot,
        }

        state.setdefault("published", []).append(published_item)
        state.setdefault("processed_slots", []).append(slot)

        state["next_video_index"] = (
            int(pending["video_index"]) + 1
        )
        state["next_title_index"] = (
            int(pending["title_index"]) + 1
        )
        state["pending_upload"] = None

        save_state(state)

        print("Publishing state saved.")
        print(f"Video URL: https://youtu.be/{video_id}")

    except Exception:
        print(
            "WARNING: Upload did not finish cleanly. "
            "The pending upload remains locked to prevent an automatic "
            "duplicate. Check YouTube manually before changing state.json."
        )
        raise

    finally:
        if local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except OSError:
                print(f"Warning: could not remove temporary file {local_path}")


# =========================================================
# MAIN
# =========================================================

def main():
    args = set(sys.argv[1:])

    known_modes = {
        "--check-slot",
        "--lock",
        "--prepare",
        "--publish",
    }

    selected_modes = args.intersection(known_modes)

    if len(selected_modes) > 1:
        raise RuntimeError(
            "Choose only one mode: --check-slot, --lock, "
            "--prepare, or --publish."
        )

    unknown_args = args - known_modes

    if unknown_args:
        raise RuntimeError(
            f"Unknown arguments: {sorted(unknown_args)}"
        )

    if "--check-slot" in args:
        cmd_check_slot()
        return

    if "--lock" in args:
        cmd_lock()
        return

    if "--prepare" in args:
        cmd_prepare()
        return

    if "--publish" in args:
        cmd_publish()
        return

    print("Dry run only. No video was published.")
    print("Available modes:")
    print("  --check-slot")
    print("  --prepare")
    print("  --lock")
    print("  --publish")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

