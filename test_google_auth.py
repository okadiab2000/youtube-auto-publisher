import json
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


REQUIRED_SCOPES = {
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
}


def main():
    token_json = os.environ.get("GOOGLE_TOKEN_JSON")
    if not token_json:
        raise RuntimeError("GOOGLE_TOKEN_JSON secret is missing")

    try:
        token_data = json.loads(token_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GOOGLE_TOKEN_JSON is not valid JSON") from exc

    granted_scopes = set(token_data.get("scopes") or [])
    missing_scopes = REQUIRED_SCOPES - granted_scopes
    if missing_scopes:
        names = ", ".join(sorted(missing_scopes))
        raise RuntimeError(
            "The saved Google token does not list all required scopes: "
            f"{names}. Re-authorize locally with drive.readonly and "
            "youtube.upload, then update the GOOGLE_TOKEN_JSON secret."
        )

    creds = Credentials.from_authorized_user_info(
        token_data,
        scopes=sorted(REQUIRED_SCOPES),
    )

    if creds.expired:
        if not creds.refresh_token:
            raise RuntimeError(
                "Google token expired and has no refresh token. "
                "Re-authorize locally and update GOOGLE_TOKEN_JSON."
            )
        creds.refresh(Request())

    if not creds.valid:
        raise RuntimeError(
            "Google credentials are invalid after refresh. "
            "Re-authorize locally and update GOOGLE_TOKEN_JSON."
        )

    drive = build(
        "drive", "v3", credentials=creds, cache_discovery=False
    )

    # Confirms the token can access Drive without changing any data.
    drive.files().list(
        pageSize=1,
        fields="files(id,name)",
    ).execute()

    # YouTube's channels.list requires a separate read scope and is not
    # necessary to verify the upload scope. Avoid requesting extra access.
    print("Google Drive API: OK")
    print("Required upload scope is present in the saved token.")
    print("No videos were uploaded and no YouTube data was changed.")


if __name__ == "__main__":
    main()
