
import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def main():
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")
    folder_id = os.environ.get("DRIVE_FOLDER_ID")

    if not token_json:
        raise RuntimeError("GOOGLE_TOKEN_JSON secret is missing")

    if not folder_id:
        raise RuntimeError("DRIVE_FOLDER_ID secret is missing")

    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(
        token_data, SCOPES
    )

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Google token is invalid. Re-authorize locally."
            )

    drive = build("drive", "v3", credentials=creds)

    query = (
        f"'{folder_id}' in parents "
        "and trashed = false "
        "and mimeType contains 'video/'"
    )

    videos = []
    page_token = None

    while len(videos) < 10:
        response = drive.files().list(
            q=query,
            pageSize=100,
            orderBy="modifiedTime asc",
            pageToken=page_token,
            fields=(
                "nextPageToken,"
                "files(id,name,mimeType,modifiedTime,size)"
            ),
        ).execute()

        videos.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    print(f"Drive folder access: OK")
    print(f"Videos found in test: {len(videos)}")

    for index, video in enumerate(videos[:10], start=1):
        print(f"\n{index}. {video['name']}")
        print(f"   Drive file ID: {video['id']}")
        print(f"   Modified: {video.get('modifiedTime', 'Unknown')}")
        print(f"   Size: {video.get('size', 'Unknown')} bytes")

    if not videos:
        print(
            "No videos found. Check the folder ID, "
            "folder contents, and Google account permissions."
        )

    print("\nTest complete. No videos were downloaded or uploaded.")


if __name__ == "__main__":
    main()
