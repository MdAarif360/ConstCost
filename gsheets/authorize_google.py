"""One-time helper: authorize this app against YOUR Google account.

This is the OAuth2 alternative to a service account: instead of sharing the
spreadsheet with a robot email, you log into your own Google account once in
a browser, and this script prints the refresh token to put in secrets. After
that, the deployed app never shows a login screen again -- it uses the saved
refresh token to act as you, silently.

Setup (one time):

1. In the Google Cloud console, enable the Google Sheets API and Google
   Drive API for a project.
2. Go to "APIs & Services -> Credentials -> Create Credentials -> OAuth
   client ID", choose "Desktop app", and download the JSON file it gives you.
3. pip install google-auth-oauthlib   (only needed to run this script)
4. Run:

     python authorize_google.py path/to/client_secret.json

   A browser window opens; sign in with the Google account whose Sheets and
   Drive you want the app to use, and approve access.

The script prints a [google_oauth] TOML block. Paste it into
.streamlit/secrets.toml (or the Streamlit Cloud app secrets) alongside
GSHEETS_SPREADSHEET_ID. The spreadsheet does not need to be shared with
anyone else -- create it in your own Drive and just point
GSHEETS_SPREADSHEET_ID at it.
"""

from __future__ import annotations

import sys

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python authorize_google.py path/to/client_secret.json")
        raise SystemExit(1)

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Missing dependency. Run: pip install google-auth-oauthlib")
        raise SystemExit(1)

    client_secret_path = sys.argv[1]
    flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, scopes=SCOPES)
    credentials = flow.run_local_server(port=0)

    if not credentials.refresh_token:
        print(
            "Google did not return a refresh token. This usually happens when "
            "re-authorizing the same account/client. Revoke the app's access at "
            "https://myaccount.google.com/permissions and run this script again."
        )
        raise SystemExit(1)

    print("\nAuthorization complete. Add this to .streamlit/secrets.toml:\n")
    print("[google_oauth]")
    print(f'client_id = "{credentials.client_id}"')
    print(f'client_secret = "{credentials.client_secret}"')
    print(f'refresh_token = "{credentials.refresh_token}"')
    print(
        "\nAlso set GSHEETS_SPREADSHEET_ID to a sheet in your own Drive -- no "
        "sharing step needed, since the app now acts as this Google account."
    )


if __name__ == "__main__":
    main()
