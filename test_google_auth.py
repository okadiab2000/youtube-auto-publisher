
import json
import os
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]

def main():
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("GOOGLE_TOKEN_JSON secret is missing")

    token_data = json.loads(token_json)
    creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise RuntimeError(
                "Google token is invalid or expired. Re-authorize locally."
            )

    drive = build("drive", "v3", credentials=creds)
    youtube = build("youtube", "v3", credentials=creds)

    drive.files().list(
        pageSize=1,
        fields="files(id,name)"
    ).execute()

    channel = youtube.channels().list(
        part="snippet",
        mine=True
    ).execute()

    if not channel.get("items"):
        raise RuntimeError(
            "No YouTube channel was returned for this Google account."
        )

    print("Google Drive connection: OK")
    print("YouTube API authentication: OK")
    print("Channel access confirmed. No videos were uploaded.")

if __name__ == "__main__":
    main()
