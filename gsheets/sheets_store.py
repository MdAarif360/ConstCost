"""Google Sheets storage backend for the Construction Cost Tracker.

The spreadsheet replaces the PostgreSQL/SQLite database used by the original
app. Tabular data lives in worksheets:

    expenses        id | date | category | phase | description | amount |
                    receipt_name | receipt_type | receipt_ref | created_at
    budgets         category | amount
    app_meta        key | value
    receipt_chunks  ref | seq | data          (base64 chunks, fallback storage)

Uploaded bills are binary, so they are stored outside the expense cells:

* When ``GDRIVE_FOLDER_ID`` is configured the file is uploaded to that Google
  Drive folder and the expense row keeps ``drive:<file id>``.
* Otherwise the file is base64 encoded, split into 45,000 character chunks
  (a Sheets cell holds 50,000) and written to ``receipt_chunks``. The expense
  row then keeps ``sheet:<uuid>``.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any

import gspread
import streamlit as st
from google.oauth2.credentials import Credentials as UserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

EXPENSES_SHEET = "expenses"
BUDGETS_SHEET = "budgets"
META_SHEET = "app_meta"
CHUNKS_SHEET = "receipt_chunks"

EXPENSE_HEADER = [
    "id",
    "date",
    "category",
    "phase",
    "description",
    "amount",
    "paymenttype",
    "receipt_name",
    "receipt_type",
    "receipt_ref",
    "created_at",
]
BUDGET_HEADER = ["category", "amount"]
META_HEADER = ["key", "value"]
CHUNK_HEADER = ["ref", "seq", "data"]

SHEET_HEADERS = {
    EXPENSES_SHEET: EXPENSE_HEADER,
    BUDGETS_SHEET: BUDGET_HEADER,
    META_SHEET: META_HEADER,
    CHUNKS_SHEET: CHUNK_HEADER,
}

CHUNK_SIZE = 45000
CACHE_TTL_SECONDS = float(os.getenv("GSHEETS_CACHE_TTL_SECONDS", "20"))

SPREADSHEET_ID_KEYS = ("GSHEETS_SPREADSHEET_ID", "gsheets_spreadsheet_id")
SPREADSHEET_URL_KEYS = ("GSHEETS_SPREADSHEET_URL", "gsheets_spreadsheet_url")
SPREADSHEET_NAME_KEYS = ("GSHEETS_SPREADSHEET_NAME", "gsheets_spreadsheet_name")
DRIVE_FOLDER_KEYS = ("GDRIVE_FOLDER_ID", "gdrive_folder_id")
SERVICE_ACCOUNT_SECRET_NAMES = ("gcp_service_account", "google_service_account")
OAUTH_CLIENT_ID_KEYS = ("GOOGLE_OAUTH_CLIENT_ID", "google_oauth_client_id")
OAUTH_CLIENT_SECRET_KEYS = ("GOOGLE_OAUTH_CLIENT_SECRET", "google_oauth_client_secret")
OAUTH_REFRESH_TOKEN_KEYS = ("GOOGLE_OAUTH_REFRESH_TOKEN", "google_oauth_refresh_token")
OAUTH_TOKEN_URI_KEYS = ("GOOGLE_OAUTH_TOKEN_URI", "google_oauth_token_uri")
OAUTH_SECRET_NAMES = ("google_oauth",)
DEFAULT_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"
CONNECTION_SECRET_NAMES = (
    "gsheets",
    "google_sheets",
    "construction_cost",
    "cost_tracker",
)

_CREDENTIALS: Any = None
_CLIENT: Any = None
_SPREADSHEET: Any = None
_DRIVE: Any = None
_FINGERPRINT: str | None = None
_INITIALIZED_FOR: str | None = None
_CACHE: dict[str, tuple[float, list[list[Any]]]] = {}


class StorageConfigError(RuntimeError):
    """Raised when the Google Sheets backend is not configured correctly."""


# --------------------------------------------------------------- settings --


def _secret_node(*path: str) -> Any:
    try:
        node: Any = st.secrets
    except Exception:
        return None
    for key in path:
        if node is None or not hasattr(node, "get"):
            return None
        try:
            node = node.get(key)
        except Exception:
            return None
    return node


def _setting(keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    for key in keys:
        value = _secret_node(key)
        if value and str(value).strip():
            return str(value).strip()
    return None


def _connection_secret() -> Any:
    for name in CONNECTION_SECRET_NAMES:
        node = _secret_node("connections", name)
        if node is not None and hasattr(node, "get"):
            return node
    return None


def _normalize_service_account(info: Any) -> dict[str, Any]:
    if isinstance(info, str):
        candidate = info.strip()
        if candidate and not candidate.startswith("{") and os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as handle:
                candidate = handle.read()
        try:
            info = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise StorageConfigError(
                "The service account credentials are not valid JSON."
            ) from exc

    info = dict(info)
    private_key = info.get("private_key")
    if isinstance(private_key, str):
        info["private_key"] = private_key.replace("\\n", "\n")
    return info


def service_account_info() -> dict[str, Any]:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw and raw.strip():
        return _normalize_service_account(raw)

    path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if path and os.path.exists(path):
        return _normalize_service_account(path)

    for name in SERVICE_ACCOUNT_SECRET_NAMES:
        node = _secret_node(name)
        if node is not None and hasattr(node, "get"):
            return _normalize_service_account(dict(node))

    connection = _connection_secret()
    if connection is not None and connection.get("private_key"):
        info = {
            key: value
            for key, value in dict(connection).items()
            if key not in {"spreadsheet", "worksheet", "drive_folder_id"}
        }
        return _normalize_service_account(info)

    raw_secret = _secret_node("GOOGLE_SERVICE_ACCOUNT_JSON")
    if raw_secret:
        return _normalize_service_account(str(raw_secret))

    raise StorageConfigError(
        "No Google credentials found. Configure either OAuth2 as your own Google "
        "account ([google_oauth] with client_id / client_secret / refresh_token — "
        "run authorize_google.py once to generate them) or a service account "
        "([gcp_service_account] secret, or GOOGLE_SERVICE_ACCOUNT_JSON / "
        "GOOGLE_APPLICATION_CREDENTIALS)."
    )


def oauth_user_info() -> dict[str, str] | None:
    """Return OAuth2 user credentials (your own Google account) if configured."""
    client_id = _setting(OAUTH_CLIENT_ID_KEYS)
    client_secret = _setting(OAUTH_CLIENT_SECRET_KEYS)
    refresh_token = _setting(OAUTH_REFRESH_TOKEN_KEYS)

    if not (client_id and client_secret and refresh_token):
        for name in OAUTH_SECRET_NAMES:
            node = _secret_node(name)
            if node is not None and hasattr(node, "get"):
                client_id = client_id or node.get("client_id")
                client_secret = client_secret or node.get("client_secret")
                refresh_token = refresh_token or node.get("refresh_token")

        connection = _connection_secret()
        if connection is not None:
            client_id = client_id or connection.get("client_id")
            client_secret = client_secret or connection.get("client_secret")
            refresh_token = refresh_token or connection.get("refresh_token")

    if not (client_id and client_secret and refresh_token):
        return None

    token_uri = _setting(OAUTH_TOKEN_URI_KEYS) or DEFAULT_OAUTH_TOKEN_URI
    return {
        "client_id": str(client_id).strip(),
        "client_secret": str(client_secret).strip(),
        "refresh_token": str(refresh_token).strip(),
        "token_uri": str(token_uri).strip(),
    }


def spreadsheet_reference() -> tuple[str, str]:
    """Return ``(kind, value)`` where kind is ``id``, ``url`` or ``name``."""
    value = _setting(SPREADSHEET_ID_KEYS)
    if value:
        return "id", value

    value = _setting(SPREADSHEET_URL_KEYS)
    if value:
        return "url", value

    connection = _connection_secret()
    if connection is not None:
        candidate = connection.get("spreadsheet")
        if candidate:
            candidate = str(candidate).strip()
            if candidate.startswith("http"):
                return "url", candidate
            if re.fullmatch(r"[A-Za-z0-9_-]{30,}", candidate):
                return "id", candidate
            return "name", candidate

    value = _setting(SPREADSHEET_NAME_KEYS)
    if value:
        return "name", value

    raise StorageConfigError(
        "No spreadsheet configured. Set GSHEETS_SPREADSHEET_ID (or "
        "GSHEETS_SPREADSHEET_URL / GSHEETS_SPREADSHEET_NAME) in the app secrets."
    )


def drive_folder_id() -> str | None:
    value = _setting(DRIVE_FOLDER_KEYS)
    if value:
        return value
    connection = _connection_secret()
    if connection is not None:
        candidate = connection.get("drive_folder_id")
        if candidate:
            return str(candidate).strip()
    return None


# ------------------------------------------------------------- connection --


def _resolve_credentials() -> tuple[Any, str, str | None]:
    """Return ``(credentials, fingerprint_seed, share_hint)``.

    ``share_hint`` is the identity to tell the user to share the spreadsheet
    with (a service account email), or ``None`` when the credentials are the
    user's own Google account and no sharing is needed.
    """
    oauth_info = oauth_user_info()
    if oauth_info is not None:
        credentials = UserCredentials(
            token=None,
            refresh_token=oauth_info["refresh_token"],
            token_uri=oauth_info["token_uri"],
            client_id=oauth_info["client_id"],
            client_secret=oauth_info["client_secret"],
            scopes=SCOPES,
        )
        return credentials, f"oauth:{oauth_info['client_id']}", None

    info = service_account_info()
    missing = [key for key in ("client_email", "private_key") if not info.get(key)]
    if missing:
        raise StorageConfigError(
            f"The service account credentials are missing: {', '.join(missing)}."
        )
    credentials = ServiceAccountCredentials.from_service_account_info(
        info, scopes=SCOPES
    )
    return credentials, f"service:{info.get('client_email', '')}", info.get("client_email")


def _connect() -> Any:
    global _CREDENTIALS, _CLIENT, _SPREADSHEET, _DRIVE, _FINGERPRINT

    credentials, credential_seed, share_hint = _resolve_credentials()
    kind, reference = spreadsheet_reference()
    fingerprint = f"{credential_seed}|{kind}:{reference}"

    if _SPREADSHEET is not None and _FINGERPRINT == fingerprint:
        return _SPREADSHEET

    try:
        client = gspread.authorize(credentials)
    except Exception as exc:
        raise StorageConfigError(
            f"Could not authenticate with Google: {exc}"
        ) from exc

    share_note = (
        f"Share it with {share_hint} as an Editor and "
        if share_hint
        else "Make sure the Google account used to authorize has access to it, and "
    )

    try:
        if kind == "id":
            spreadsheet = client.open_by_key(reference)
        elif kind == "url":
            spreadsheet = client.open_by_url(reference)
        else:
            spreadsheet = client.open(reference)
    except gspread.SpreadsheetNotFound as exc:
        raise StorageConfigError(
            f"Spreadsheet {reference!r} was not found. {share_note}check the id or URL."
        ) from exc
    except gspread.exceptions.APIError as exc:
        raise StorageConfigError(
            f"Google rejected the spreadsheet request: {exc} {share_note}make sure "
            "the Google Sheets API and Google Drive API are enabled for the project."
        ) from exc

    _CREDENTIALS = credentials
    _CLIENT = client
    _SPREADSHEET = spreadsheet
    _DRIVE = None
    _FINGERPRINT = fingerprint
    _CACHE.clear()
    return spreadsheet


def _drive_service() -> Any:
    global _DRIVE
    _connect()
    if _DRIVE is None:
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:  # pragma: no cover - depends on install
            raise StorageConfigError(
                "google-api-python-client is required to store bills in Google "
                "Drive. Install it, or clear GDRIVE_FOLDER_ID to keep bills "
                "inside the spreadsheet."
            ) from exc
        _DRIVE = build("drive", "v3", credentials=_CREDENTIALS, cache_discovery=False)
    return _DRIVE


# ----------------------------------------------------------- sheet helpers --


def _column_letter(index: int) -> str:
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


EXPENSE_LAST_COLUMN = _column_letter(len(EXPENSE_HEADER))


def _worksheet(title: str) -> Any:
    spreadsheet = _connect()
    header = SHEET_HEADERS[title]
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=title, rows=200, cols=max(len(header), 4)
        )
        worksheet.update(
            range_name=f"A1:{_column_letter(len(header))}1",
            values=[header],
            value_input_option="RAW",
        )
        _CACHE.pop(title, None)
    return worksheet


def _values(title: str, refresh: bool = False) -> list[list[Any]]:
    now = time.monotonic()
    cached = _CACHE.get(title)
    if not refresh and cached is not None and (now - cached[0]) < CACHE_TTL_SECONDS:
        return cached[1]

    values = _worksheet(title).get_all_values()
    _CACHE[title] = (time.monotonic(), values)
    return values


def _rows(title: str, refresh: bool = False) -> list[list[Any]]:
    values = _values(title, refresh=refresh)
    return values[1:] if len(values) > 1 else []


def _invalidate(*titles: str) -> None:
    for title in titles:
        _CACHE.pop(title, None)


def _padded(row: list[Any], width: int) -> list[Any]:
    row = list(row)
    if len(row) < width:
        row.extend([""] * (width - len(row)))
    return row[:width]


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _to_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if cleaned in {"", ".", "-", "-."}:
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def _delete_sheet_rows(worksheet: Any, row_numbers: list[int]) -> None:
    """Delete 1-based sheet rows (never the header) in a single batch request."""
    unique_rows = sorted({row for row in row_numbers if row > 1}, reverse=True)
    if not unique_rows:
        return
    requests = [
        {
            "deleteDimension": {
                "range": {
                    "sheetId": worksheet.id,
                    "dimension": "ROWS",
                    "startIndex": row - 1,
                    "endIndex": row,
                }
            }
        }
        for row in unique_rows
    ]
    worksheet.spreadsheet.batch_update({"requests": requests})


# ------------------------------------------------------------------ bills --


def _store_receipt_bytes(name: str, mime_type: str, data: bytes) -> str:
    folder = drive_folder_id()
    if folder:
        return f"drive:{_drive_upload(name, mime_type, data, folder)}"

    ref = f"sheet:{uuid.uuid4().hex}"
    encoded = base64.b64encode(data).decode("ascii")
    chunks = [
        [ref, index, encoded[start : start + CHUNK_SIZE]]
        for index, start in enumerate(range(0, len(encoded), CHUNK_SIZE))
    ] or [[ref, 0, ""]]
    _worksheet(CHUNKS_SHEET).append_rows(chunks, value_input_option="RAW")
    _invalidate(CHUNKS_SHEET)
    return ref


def _drive_upload(name: str, mime_type: str, data: bytes, folder: str) -> str:
    from googleapiclient.http import MediaIoBaseUpload

    media = MediaIoBaseUpload(
        io.BytesIO(data),
        mimetype=mime_type or "application/octet-stream",
        resumable=False,
    )
    created = (
        _drive_service()
        .files()
        .create(
            body={"name": name, "parents": [folder]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def _drive_download(file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    buffer = io.BytesIO()
    request = _drive_service().files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


def _delete_receipt_artifact(ref: str | None) -> None:
    if not ref:
        return

    if ref.startswith("drive:"):
        try:
            _drive_service().files().delete(
                fileId=ref[len("drive:") :], supportsAllDrives=True
            ).execute()
        except Exception:
            pass
        return

    if ref.startswith("sheet:"):
        worksheet = _worksheet(CHUNKS_SHEET)
        targets = [
            index + 2
            for index, row in enumerate(_rows(CHUNKS_SHEET, refresh=True))
            if _padded(row, len(CHUNK_HEADER))[0] == ref
        ]
        _delete_sheet_rows(worksheet, targets)
        _invalidate(CHUNKS_SHEET)


@st.cache_data(show_spinner=False, max_entries=128)
def fetch_receipt(ref: str | None) -> bytes | None:
    """Load the bytes of a stored bill. Cached: Sheets and Drive round trips are slow."""
    if not ref:
        return None

    if ref.startswith("drive:"):
        try:
            return _drive_download(ref[len("drive:") :])
        except Exception:
            return None

    if ref.startswith("sheet:"):
        pieces: list[tuple[int, str]] = []
        for row in _rows(CHUNKS_SHEET):
            padded = _padded(row, len(CHUNK_HEADER))
            if padded[0] == ref:
                pieces.append((int(_to_float(padded[1])), _text(padded[2])))
        if not pieces:
            return None
        encoded = "".join(piece for _, piece in sorted(pieces))
        try:
            return base64.b64decode(encoded)
        except Exception:
            return None

    return None


# ---------------------------------------------------------------- records --


def _expense_row(expense: dict[str, Any], created_at: str, receipt_ref: str) -> list[Any]:
    return [
        _text(expense.get("id")),
        _text(expense.get("date")),
        _text(expense.get("category")),
        _text(expense.get("phase")),
        _text(expense.get("description")),
        float(expense.get("amount") or 0.0),
        _text(expense.get("paymenttype")),
        _text(expense.get("receipt_name")),
        _text(expense.get("receipt_type")),
        receipt_ref,
        created_at,
    ]


def _expense_record(row: list[Any]) -> dict[str, Any]:
    padded = _padded(row, len(EXPENSE_HEADER))
    return {
        "id": _text(padded[0]),
        "date": _text(padded[1]),
        "category": _text(padded[2]),
        "phase": _text(padded[3]) or "General",
        "description": _text(padded[4]),
        "amount": _to_float(padded[5]),
        "paymenttype": _text(padded[6]),
        "receipt_name": _text(padded[7]) or None,
        "receipt_type": _text(padded[8]) or None,
        "receipt_ref": _text(padded[9]) or None,
        "created_at": _text(padded[10]),
    }


def _expense_rows_by_id(refresh: bool = False) -> dict[str, tuple[int, list[Any]]]:
    """Map expense id -> (1-based sheet row number, padded row values)."""
    mapping: dict[str, tuple[int, list[Any]]] = {}
    for index, row in enumerate(_rows(EXPENSES_SHEET, refresh=refresh)):
        padded = _padded(row, len(EXPENSE_HEADER))
        expense_id = _text(padded[0])
        if expense_id:
            mapping[expense_id] = (index + 2, padded)
    return mapping


def _now() -> str:
    return datetime.utcnow().isoformat()


# ------------------------------------------------------------- public API --


def initialize_storage(
    seed_expenses: list[dict[str, Any]],
    default_budgets: dict[str, float],
) -> None:
    """Create the worksheets, default budgets and seed rows once per process."""
    global _INITIALIZED_FOR

    _connect()
    if _INITIALIZED_FOR == _FINGERPRINT:
        return

    for title in (EXPENSES_SHEET, BUDGETS_SHEET, META_SHEET, CHUNKS_SHEET):
        worksheet = _worksheet(title)
        header = SHEET_HEADERS[title]
        values = _values(title, refresh=True)
        if not values or not any(_text(cell) for cell in values[0]):
            worksheet.update(
                range_name=f"A1:{_column_letter(len(header))}1",
                values=[header],
                value_input_option="RAW",
            )
            _invalidate(title)

    existing_budgets = {
        _text(_padded(row, len(BUDGET_HEADER))[0]) for row in _rows(BUDGETS_SHEET)
    }
    missing_budgets = [
        [category, float(amount)]
        for category, amount in default_budgets.items()
        if category not in existing_budgets
    ]
    if missing_budgets:
        _worksheet(BUDGETS_SHEET).append_rows(missing_budgets, value_input_option="RAW")
        _invalidate(BUDGETS_SHEET)

    meta = {
        _text(_padded(row, len(META_HEADER))[0]): _text(_padded(row, len(META_HEADER))[1])
        for row in _rows(META_SHEET)
    }
    if not meta.get("seeded"):
        if not _rows(EXPENSES_SHEET) and seed_expenses:
            created_at = _now()
            _worksheet(EXPENSES_SHEET).append_rows(
                [_expense_row(expense, created_at, "") for expense in seed_expenses],
                value_input_option="RAW",
            )
            _invalidate(EXPENSES_SHEET)
        _worksheet(META_SHEET).append_rows([["seeded", "1"]], value_input_option="RAW")
        _invalidate(META_SHEET)

    _INITIALIZED_FOR = _FINGERPRINT


def load_expenses() -> list[dict[str, Any]]:
    records = [
        _expense_record(row)
        for row in _rows(EXPENSES_SHEET)
        if _text(_padded(row, 1)[0])
    ]
    records.sort(
        key=lambda item: (item["date"], item["created_at"], item["id"]),
        reverse=True,
    )
    return records


def load_budgets(default_budgets: dict[str, float]) -> dict[str, float]:
    budgets = dict(default_budgets)
    for row in _rows(BUDGETS_SHEET):
        padded = _padded(row, len(BUDGET_HEADER))
        category = _text(padded[0])
        if category in budgets:
            budgets[category] = _to_float(padded[1], budgets[category])
    return budgets


def save_budget(category: str, amount: float) -> None:
    worksheet = _worksheet(BUDGETS_SHEET)
    for index, row in enumerate(_rows(BUDGETS_SHEET, refresh=True)):
        if _text(_padded(row, len(BUDGET_HEADER))[0]) == category:
            worksheet.update(
                range_name=f"A{index + 2}:B{index + 2}",
                values=[[category, float(amount)]],
                value_input_option="RAW",
            )
            _invalidate(BUDGETS_SHEET)
            return

    worksheet.append_rows([[category, float(amount)]], value_input_option="RAW")
    _invalidate(BUDGETS_SHEET)


def save_expense(expense: dict[str, Any]) -> dict[str, Any]:
    """Insert or update one expense. Returns the record as it is now stored."""
    worksheet = _worksheet(EXPENSES_SHEET)
    existing = _expense_rows_by_id(refresh=True)
    previous = existing.get(_text(expense.get("id")))

    receipt_ref = _text(expense.get("receipt_ref"))
    receipt_bytes = expense.get("receipt_bytes")
    if receipt_bytes:
        if previous is not None:
            _delete_receipt_artifact(_text(previous[1][8]) or None)
        receipt_ref = _store_receipt_bytes(
            _text(expense.get("receipt_name")) or "bill",
            _text(expense.get("receipt_type")) or "application/octet-stream",
            receipt_bytes,
        )
        fetch_receipt.clear()
    elif previous is not None and not receipt_ref:
        receipt_ref = _text(previous[1][8])

    created_at = _text(previous[1][9]) if previous is not None else ""
    row = _expense_row(expense, created_at or _now(), receipt_ref)

    if previous is None:
        worksheet.append_rows([row], value_input_option="RAW")
    else:
        row_number = previous[0]
        worksheet.update(
            range_name=f"A{row_number}:{EXPENSE_LAST_COLUMN}{row_number}",
            values=[row],
            value_input_option="RAW",
        )

    _invalidate(EXPENSES_SHEET)
    return _expense_record(row)


def save_expenses(expenses: list[dict[str, Any]]) -> None:
    """Bulk insert/update, used by the CSV import."""
    if not expenses:
        return

    worksheet = _worksheet(EXPENSES_SHEET)
    existing = _expense_rows_by_id(refresh=True)
    created_at = _now()

    appended: list[list[Any]] = []
    updates: list[dict[str, Any]] = []

    for expense in expenses:
        previous = existing.get(_text(expense.get("id")))
        receipt_ref = _text(expense.get("receipt_ref"))
        receipt_bytes = expense.get("receipt_bytes")
        if receipt_bytes:
            receipt_ref = _store_receipt_bytes(
                _text(expense.get("receipt_name")) or "bill",
                _text(expense.get("receipt_type")) or "application/octet-stream",
                receipt_bytes,
            )
        elif previous is not None and not receipt_ref:
            receipt_ref = _text(previous[1][8])

        if previous is None:
            appended.append(_expense_row(expense, created_at, receipt_ref))
        else:
            row_number = previous[0]
            updates.append(
                {
                    "range": f"A{row_number}:{EXPENSE_LAST_COLUMN}{row_number}",
                    "values": [
                        _expense_row(
                            expense, _text(previous[1][9]) or created_at, receipt_ref
                        )
                    ],
                }
            )

    if updates:
        worksheet.batch_update(updates, value_input_option="RAW")
    if appended:
        worksheet.append_rows(appended, value_input_option="RAW")
    _invalidate(EXPENSES_SHEET)


def update_expense_details(expense: dict[str, Any]) -> None:
    """Update the editable columns (date .. amount) without touching the bill."""
    worksheet = _worksheet(EXPENSES_SHEET)
    previous = _expense_rows_by_id(refresh=True).get(_text(expense.get("id")))
    if previous is None:
        save_expense(expense)
        return

    row_number = previous[0]
    worksheet.update(
        range_name=f"B{row_number}:F{row_number}",
        values=[
            [
                _text(expense.get("date")),
                _text(expense.get("category")),
                _text(expense.get("phase")),
                _text(expense.get("description")),
                _text(expense.get("paymenttype")),
                float(expense.get("amount") or 0.0),                
            ]
        ],
        value_input_option="RAW",
    )
    _invalidate(EXPENSES_SHEET)


def delete_expense(expense_id: str) -> None:
    worksheet = _worksheet(EXPENSES_SHEET)
    previous = _expense_rows_by_id(refresh=True).get(_text(expense_id))
    if previous is None:
        return

    _delete_receipt_artifact(_text(previous[1][8]) or None)
    _delete_sheet_rows(worksheet, [previous[0]])
    _invalidate(EXPENSES_SHEET)
    fetch_receipt.clear()


def clear_expenses() -> None:
    worksheet = _worksheet(EXPENSES_SHEET)
    rows = _rows(EXPENSES_SHEET, refresh=True)
    for row in rows:
        _delete_receipt_artifact(_text(_padded(row, len(EXPENSE_HEADER))[8]) or None)
    if rows:
        _delete_sheet_rows(worksheet, list(range(2, len(rows) + 2)))
    _invalidate(EXPENSES_SHEET)
    fetch_receipt.clear()


def attach_receipt(
    expense_id: str,
    receipt_name: str,
    receipt_type: str,
    receipt_bytes: bytes,
) -> str | None:
    worksheet = _worksheet(EXPENSES_SHEET)
    previous = _expense_rows_by_id(refresh=True).get(_text(expense_id))
    if previous is None:
        return None

    _delete_receipt_artifact(_text(previous[1][8]) or None)
    receipt_ref = _store_receipt_bytes(receipt_name, receipt_type, receipt_bytes)
    row_number = previous[0]
    worksheet.update(
        range_name=f"G{row_number}:I{row_number}",
        values=[[receipt_name, receipt_type, receipt_ref]],
        value_input_option="RAW",
    )
    _invalidate(EXPENSES_SHEET)
    fetch_receipt.clear()
    return receipt_ref


def remove_receipt(expense_id: str) -> None:
    worksheet = _worksheet(EXPENSES_SHEET)
    previous = _expense_rows_by_id(refresh=True).get(_text(expense_id))
    if previous is None:
        return

    _delete_receipt_artifact(_text(previous[1][8]) or None)
    row_number = previous[0]
    worksheet.update(
        range_name=f"G{row_number}:I{row_number}",
        values=[["", "", ""]],
        value_input_option="RAW",
    )
    _invalidate(EXPENSES_SHEET)
    fetch_receipt.clear()


def storage_label() -> str:
    spreadsheet = _connect()
    folder = drive_folder_id()
    bills = (
        f"Google Drive folder {folder}" if folder else f'the "{CHUNKS_SHEET}" worksheet'
    )
    return f'Google Sheet "{spreadsheet.title}" (bills in {bills})'


def spreadsheet_url() -> str | None:
    try:
        return _connect().url
    except StorageConfigError:
        return None
