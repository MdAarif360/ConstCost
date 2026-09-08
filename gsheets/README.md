# Construction Cost Tracker — Google Sheets backend

An alternate version of the tracker in the repository root. The user interface is
the same; the storage layer is a Google Sheet instead of Supabase/PostgreSQL.

Nothing outside this folder is needed — `app.py` here is self-contained and the
root `app.py` still runs against PostgreSQL/SQLite.

## What lives where

The spreadsheet is created for you on first run (worksheets, headers, default
budgets and the seed expenses):

| Worksheet        | Columns                                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------------------------------- |
| `expenses`       | `id`, `date`, `category`, `phase`, `description`, `amount`, `receipt_name`, `receipt_type`, `receipt_ref`, `created_at` |
| `budgets`        | `category`, `amount`                                                                                          |
| `app_meta`       | `key`, `value` (holds the `seeded` flag)                                                                      |
| `receipt_chunks` | `ref`, `seq`, `data` (base64 pieces of uploaded bills)                                                         |

Bills are binary, so they are not written into the expense row itself:

- **With `GDRIVE_FOLDER_ID` set (recommended):** the file is uploaded to that
  Google Drive folder and the expense row keeps `drive:<file id>`.
- **Without it:** the file is base64 encoded, split into 45,000 character pieces
  (a Sheets cell holds 50,000) and written to `receipt_chunks`; the expense row
  keeps `sheet:<uuid>`. Fine for a handful of photos, slow for large PDFs.

Rows stay readable and editable by hand in the browser. Keep `id` and the ISO
`date` format (`YYYY-MM-DD`) intact; amounts may be formatted however you like,
they are parsed tolerantly.

## Setup

There are two ways to authenticate. Pick one.

### Option A — your own Google account (OAuth2, no sharing step)

The app acts as you: the sheet lives in your own Drive, nothing needs to be
shared with anyone.

1. In the Google Cloud console, enable **Google Sheets API** and **Google
   Drive API** for a project.
2. **APIs & Services → Credentials → Create Credentials → OAuth client ID**,
   application type **Desktop app**. Download the JSON file it gives you.
3. `pip install google-auth-oauthlib` (only needed for this one-time step).
4. Run:

   ```bash
   python authorize_google.py path/to/client_secret.json
   ```

   A browser opens; sign in with the Google account whose Sheets/Drive you
   want to use, and approve access. This is a real, standard Google OAuth
   consent screen — your password is typed into Google's own login page, the
   app never sees it.
5. The script prints a `[google_oauth]` block. Copy it into
   `.streamlit/secrets.toml`.
6. Create a Google Sheet in your own Drive, copy its id from the URL
   (`https://docs.google.com/spreadsheets/d/`**`<id>`**`/edit`), and set
   `GSHEETS_SPREADSHEET_ID` to it.

```toml
GSHEETS_SPREADSHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"

[google_oauth]
client_id = "...apps.googleusercontent.com"
client_secret = "..."
refresh_token = "..."
```

The refresh token does not expire from use and survives restarts, so this is
a one-time setup — no login screen appears again after this.

### Option B — a service account (robot identity)

No login flow, but the sheet has to be shared with a robot email address, and
files it creates belong to that robot, not you.

1. In the Google Cloud console, enable **Google Sheets API** and **Google
   Drive API**.
2. **IAM & Admin → Service Accounts**, create one, then **Keys → Add key →
   Create new key → JSON** and download the file.
3. Create a Google Sheet and share it with the key's `client_email` as
   **Editor**.
4. Optional, for Drive-hosted bills: create a Drive folder, share it with the
   same `client_email` as **Editor**, and copy its id from the folder URL.

```toml
GSHEETS_SPREADSHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
# GDRIVE_FOLDER_ID = "1FolderIdSharedWithTheServiceAccount"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key = "-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----\n"
client_email = "cost-tracker@your-project-id.iam.gserviceaccount.com"
token_uri = "https://oauth2.googleapis.com/token"
```

### Secrets file

Copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` and fill in
whichever block you used above. It is git-ignored — never commit either
credential set. If both `[google_oauth]` and `[gcp_service_account]` are
present, OAuth wins.

Environment variables work too, which is handy for Docker or a VPS:

| Variable                         | Purpose                                            |
| -------------------------------- | -------------------------------------------------- |
| `GSHEETS_SPREADSHEET_ID`         | Target spreadsheet id                              |
| `GSHEETS_SPREADSHEET_URL`        | Full sheet URL, instead of the id                  |
| `GSHEETS_SPREADSHEET_NAME`       | Sheet title, instead of the id                     |
| `GOOGLE_OAUTH_CLIENT_ID`         | OAuth2 client id (Option A)                        |
| `GOOGLE_OAUTH_CLIENT_SECRET`     | OAuth2 client secret (Option A)                    |
| `GOOGLE_OAUTH_REFRESH_TOKEN`     | OAuth2 refresh token (Option A)                    |
| `GOOGLE_SERVICE_ACCOUNT_JSON`    | The key as raw JSON, or a path to the JSON file (Option B) |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the JSON key file (Option B)               |
| `GDRIVE_FOLDER_ID`               | Drive folder for uploaded bills                    |
| `GSHEETS_CACHE_TTL_SECONDS`      | Read-cache window, default `20`                    |

A `[connections.gsheets]` section holding either credential set's fields plus
a `spreadsheet` key is also accepted.

If nothing is configured, the app starts anyway and shows the setup
instructions instead of the dashboard.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

On macOS or Linux, activate with `source .venv/bin/activate`.

## Verifying the backend without Google

`test_sheets_store.py` runs the whole storage layer against an in-memory fake of
the Sheets API - no dependencies, no credentials, no network:

```bash
python test_sheets_store.py
```

It covers seeding, idempotent initialization, budget and expense upserts, bulk
CSV import, bill chunking and round-trip, bill replacement and removal, row
deletion, clear-all, tolerant parsing of hand-edited cells, and OAuth2 vs.
service account credential resolution.

## Deploy to Streamlit Community Cloud

1. Push this repository to GitHub.
2. Create a new app and set the main file path to `gsheets/app.py`.
3. Paste the contents of your `secrets.toml` into the app's **Secrets** box.
4. Deploy. On Cloud, `requirements.txt` is resolved from the repository root, so
   either deploy this folder as its own repository or merge these dependencies
   into the root `requirements.txt`.

## Trade-offs versus the PostgreSQL version

- **Speed.** Every read and write is an HTTPS call to Google. Sheet reads are
  cached for `GSHEETS_CACHE_TTL_SECONDS` (default 20s) so a burst of Streamlit
  reruns does not hammer the API, and bill downloads are cached per session.
- **Quotas.** Google allows 300 read and 300 write requests per minute per
  project, 60 per minute per user. Comfortable for a few concurrent editors.
- **No transactions.** Two people editing the same expense at the same moment
  can overwrite each other — last write wins. PostgreSQL does not have this
  problem.
- **Row addressing.** Updates target a row found by `id`. Inserting or deleting
  rows by hand while the app is open is safe: each write re-reads the sheet
  first to locate the row.
- **Size.** A spreadsheet holds up to 10 million cells. With bills kept in Drive
  that is effectively unlimited for this app; with bills in `receipt_chunks`,
  budget roughly 1 row per 33 KB of file.
- **Visibility.** The upside: the data is a normal spreadsheet. Anyone with
  access can filter, chart or export it without touching the app.
