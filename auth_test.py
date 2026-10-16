
# import os.path

# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from googleapiclient.discovery import build

# SCOPES = [
#     "https://www.googleapis.com/auth/drive.readonly",
#     "https://www.googleapis.com/auth/youtube.upload",
# ]

# def main():
#     creds = None

#     if os.path.exists("token.json"):
#         creds = Credentials.from_authorized_user_file(
#             "token.json", SCOPES
#         )

#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             creds.refresh(Request())
#         else:
#             flow = InstalledAppFlow.from_client_secrets_file(
#                 "credentials.json", SCOPES
#             )
#             creds = flow.run_local_server(port=0)

#         with open("token.json", "w", encoding="utf-8") as token:
#             token.write(creds.to_json())

#     drive = build("drive", "v3", credentials=creds)
#     youtube = build("youtube", "v3", credentials=creds)

#     response = drive.files().list(
#         pageSize=5,
#         fields="files(id, name, mimeType)"
#     ).execute()

#     print("Google authentication successful!")
#     print("\nFiles visible in Google Drive:")

#     for file in response.get("files", []):
#         print(f"- {file['name']} ({file['mimeType']})")

#     print("\nYouTube API client initialized successfully.")

# if __name__ == "__main__":
#     main()


import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]


def main():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json", SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    drive = build("drive", "v3", credentials=creds)
    youtube = build("youtube", "v3", credentials=creds)

    response = drive.files().list(
        pageSize=5,
        fields="files(id,name,mimeType)"
    ).execute()

    print("Google authentication successful!")
    print("\nFirst files visible in Google Drive:")

    for item in response.get("files", []):
        print(f"- {item['name']} ({item['mimeType']})")

    print("\nYouTube API client initialized successfully.")


if __name__ == "__main__":
    main()
