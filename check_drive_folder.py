
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

FOLDER_ID = "1iiUPSTGe0SVsCkjofChkEW4MaceIhXSY"

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]


def main():
    creds = Credentials.from_authorized_user_file(
        "token.json",
        SCOPES,
    )

    drive = build("drive", "v3", credentials=creds)

    files = []
    page_token = None

    while True:
        result = drive.files().list(
            q=f"'{FOLDER_ID}' in parents and trashed = false",
            pageSize=1000,
            pageToken=page_token,
            orderBy="name",
            fields="nextPageToken,files(id,name,mimeType,modifiedTime,size)",
        ).execute()

        files.extend(result.get("files", []))
        page_token = result.get("nextPageToken")

        if not page_token:
            break

    videos = [
        item for item in files
        if item["mimeType"].startswith("video/")
    ]

    print(f"Total items in folder: {len(files)}")
    print(f"Video files in folder: {len(videos)}")
    print("\nFirst 10 video names:")

    for item in videos[:10]:
        print(item["name"])


if __name__ == "__main__":
    main()
