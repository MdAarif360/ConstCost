"""Exercise sheets_store.py against an in-memory fake of the Google Sheets API.

Run with plain Python -- no dependencies, no Google credentials, no network:

    python test_sheets_store.py
"""

from __future__ import annotations

import os
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


# ----------------------------------------------------------- streamlit stub --
class _Secrets(dict):
    pass


def _cache_data(*dargs, **dkwargs):
    def decorator(func):
        cache = {}

        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            if key not in cache:
                cache[key] = func(*args, **kwargs)
            return cache[key]

        wrapper.clear = cache.clear
        return wrapper

    if dargs and callable(dargs[0]) and not dkwargs:
        return decorator(dargs[0])
    return decorator


streamlit_stub = types.ModuleType("streamlit")
streamlit_stub.secrets = _Secrets()
streamlit_stub.cache_data = _cache_data
sys.modules["streamlit"] = streamlit_stub


# -------------------------------------------------------- google-auth stub --
google_pkg = types.ModuleType("google")
oauth2_pkg = types.ModuleType("google.oauth2")
sa_mod = types.ModuleType("google.oauth2.service_account")
creds_mod = types.ModuleType("google.oauth2.credentials")


class ServiceAccountCredentials:
    def __init__(self, info):
        self.info = info

    @classmethod
    def from_service_account_info(cls, info, scopes=None):
        return cls(info)


class UserCredentials:
    def __init__(self, token, refresh_token, token_uri, client_id, client_secret, scopes=None):
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_uri = token_uri


sa_mod.Credentials = ServiceAccountCredentials
creds_mod.Credentials = UserCredentials
oauth2_pkg.service_account = sa_mod
oauth2_pkg.credentials = creds_mod
google_pkg.oauth2 = oauth2_pkg
sys.modules["google"] = google_pkg
sys.modules["google.oauth2"] = oauth2_pkg
sys.modules["google.oauth2.service_account"] = sa_mod
sys.modules["google.oauth2.credentials"] = creds_mod


# ------------------------------------------------------------ gspread stub --
CALL_LOG: list[str] = []


class SpreadsheetNotFound(Exception):
    pass


class WorksheetNotFound(Exception):
    pass


class APIError(Exception):
    pass


def _cell_ref(ref: str) -> tuple[int, int]:
    match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
    column = 0
    for char in match.group(1):
        column = column * 26 + (ord(char) - 64)
    return int(match.group(2)), column


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


class FakeWorksheet:
    def __init__(self, spreadsheet, title, sheet_id):
        self.spreadsheet = spreadsheet
        self.title = title
        self.id = sheet_id
        self.cells: list[list] = []

    # -- helpers ------------------------------------------------------------
    def _ensure(self, row: int, column: int) -> None:
        while len(self.cells) < row:
            self.cells.append([])
        line = self.cells[row - 1]
        while len(line) < column:
            line.append("")

    def get_all_values(self):
        CALL_LOG.append(f"read:{self.title}")
        width = max((len(row) for row in self.cells), default=0)
        out = []
        for row in self.cells:
            out.append([_as_text(cell) for cell in row] + [""] * (width - len(row)))
        while out and not any(cell for cell in out[-1]):
            out.pop()
        return out

    # -- write API ----------------------------------------------------------
    def update(self, range_name=None, values=None, value_input_option=None):
        CALL_LOG.append(f"update:{self.title}:{range_name}")
        start = range_name.split(":")[0]
        row, column = _cell_ref(start)
        for row_offset, line in enumerate(values):
            for column_offset, value in enumerate(line):
                self._ensure(row + row_offset, column + column_offset)
                self.cells[row + row_offset - 1][column + column_offset - 1] = value

    def append_rows(self, rows, value_input_option=None):
        CALL_LOG.append(f"append:{self.title}:{len(rows)}")
        used = len(self.get_all_values())
        for offset, line in enumerate(rows):
            for column_offset, value in enumerate(line):
                self._ensure(used + offset + 1, column_offset + 1)
                self.cells[used + offset][column_offset] = value

    def batch_update(self, data, value_input_option=None):
        CALL_LOG.append(f"batch_update:{self.title}:{len(data)}")
        for item in data:
            self.update(range_name=item["range"], values=item["values"])


class FakeSpreadsheet:
    def __init__(self, title="Cost Tracker"):
        self.title = title
        self.url = "https://docs.google.com/spreadsheets/d/FAKE"
        self._worksheets: dict[str, FakeWorksheet] = {}
        self._next_id = 1

    def worksheet(self, title):
        if title not in self._worksheets:
            raise WorksheetNotFound(title)
        return self._worksheets[title]

    def add_worksheet(self, title, rows, cols):
        CALL_LOG.append(f"add_worksheet:{title}")
        worksheet = FakeWorksheet(self, title, self._next_id)
        self._next_id += 1
        self._worksheets[title] = worksheet
        return worksheet

    def batch_update(self, body):
        for request in body["requests"]:
            target = request["deleteDimension"]["range"]
            worksheet = next(
                ws for ws in self._worksheets.values() if ws.id == target["sheetId"]
            )
            start = target["startIndex"]
            end = target["endIndex"]
            CALL_LOG.append(f"delete_rows:{worksheet.title}:{start}-{end}")
            del worksheet.cells[start:end]


SPREADSHEET = FakeSpreadsheet()


class FakeClient:
    def open_by_key(self, key):
        return SPREADSHEET

    def open_by_url(self, url):
        return SPREADSHEET

    def open(self, title):
        return SPREADSHEET


gspread_stub = types.ModuleType("gspread")
gspread_stub.authorize = lambda credentials: FakeClient()
gspread_stub.SpreadsheetNotFound = SpreadsheetNotFound
gspread_stub.WorksheetNotFound = WorksheetNotFound
exceptions_mod = types.ModuleType("gspread.exceptions")
exceptions_mod.APIError = APIError
gspread_stub.exceptions = exceptions_mod
gspread_stub.Worksheet = FakeWorksheet
sys.modules["gspread"] = gspread_stub
sys.modules["gspread.exceptions"] = exceptions_mod


# -------------------------------------------------------------------- test --
os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = (
    '{"client_email": "bot@example.iam.gserviceaccount.com", "private_key": "KEY"}'
)
os.environ["GSHEETS_SPREADSHEET_ID"] = "FAKE_SPREADSHEET_ID"
os.environ["GSHEETS_CACHE_TTL_SECONDS"] = "0"

import sheets_store as store  # noqa: E402

FAILURES: list[str] = []


def check(label, condition, detail=""):
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label} {detail}")
        FAILURES.append(label)


DEFAULT_BUDGETS = {
    "Labour": 5000000.0,
    "Material": 5000000.0,
    "ServiceCharge": 1500000.0,
    "Misc": 250000.0,
}
SEED = [
    {
        "id": "e1",
        "date": "2026-01-15",
        "category": "Material",
        "phase": "Foundation",
        "description": "Cement",
        "amount": 110000.0,
    },
    {
        "id": "e2",
        "date": "2026-01-18",
        "category": "Labour",
        "phase": "Foundation",
        "description": "Excavation",
        "amount": 65000.0,
    },
]

print("\n[1] initialize + seed")
store.initialize_storage(SEED, DEFAULT_BUDGETS)
expenses = store.load_expenses()
check("seeded 2 expenses", len(expenses) == 2, expenses)
check("newest first", expenses[0]["id"] == "e2", [e["id"] for e in expenses])
check("amount parsed", expenses[0]["amount"] == 65000.0, expenses[0])
budgets = store.load_budgets(DEFAULT_BUDGETS)
check("budgets default", budgets == DEFAULT_BUDGETS, budgets)

print("\n[2] initialize is idempotent")
store._INITIALIZED_FOR = None  # force a second full pass
store.initialize_storage(SEED, DEFAULT_BUDGETS)
check("no duplicate seed rows", len(store.load_expenses()) == 2)
check(
    "no duplicate budget rows",
    len(store._rows(store.BUDGETS_SHEET)) == 4,
    store._rows(store.BUDGETS_SHEET),
)
check(
    "single seeded meta row",
    len(store._rows(store.META_SHEET)) == 1,
    store._rows(store.META_SHEET),
)

print("\n[3] budgets")
store.save_budget("Material", 6000000.0)
check("budget updated", store.load_budgets(DEFAULT_BUDGETS)["Material"] == 6000000.0)
check("budget row count stable", len(store._rows(store.BUDGETS_SHEET)) == 4)

print("\n[4] insert / update one expense")
new = store.save_expense(
    {
        "id": "e3",
        "date": "2026-02-01",
        "category": "Misc",
        "phase": "General",
        "description": "Permit",
        "amount": 5000.0,
    }
)
check("insert returns record", new["id"] == "e3" and new["amount"] == 5000.0, new)
check("three expenses", len(store.load_expenses()) == 3)

store.update_expense_details(
    {
        "id": "e1",
        "date": "2026-01-16",
        "category": "Material",
        "phase": "Structure",
        "description": "Cement OPC 53",
        "amount": 111000.0,
    }
)
edited = next(e for e in store.load_expenses() if e["id"] == "e1")
check("edit applied", edited["description"] == "Cement OPC 53" and edited["amount"] == 111000.0, edited)
check("edit kept id column", edited["id"] == "e1")
check("still three expenses", len(store.load_expenses()) == 3)

print("\n[5] bulk import (append + upsert)")
store.save_expenses(
    [
        {
            "id": "e4",
            "date": "2026-03-01",
            "category": "Labour",
            "phase": "Masonry",
            "description": "Brickwork",
            "amount": 78000.0,
        },
        {
            "id": "e2",
            "date": "2026-01-19",
            "category": "Labour",
            "phase": "Foundation",
            "description": "Excavation revised",
            "amount": 66000.0,
        },
    ]
)
records = {e["id"]: e for e in store.load_expenses()}
check("bulk appended new row", "e4" in records and records["e4"]["amount"] == 78000.0)
check("bulk updated existing row", records["e2"]["description"] == "Excavation revised", records.get("e2"))
check("four expenses total", len(records) == 4, list(records))

print("\n[6] bills stored as base64 chunks in the sheet")
store.CHUNK_SIZE = 64  # force multi-chunk splitting
payload = bytes(range(256)) * 8  # 2048 bytes -> many chunks
ref = store.attach_receipt("e4", "bill.pdf", "application/pdf", payload)
check("ref is a sheet ref", bool(ref) and ref.startswith("sheet:"), ref)
chunk_rows = [r for r in store._rows(store.CHUNKS_SHEET) if r[0] == ref]
check("split into >1 chunk", len(chunk_rows) > 1, len(chunk_rows))
record = next(e for e in store.load_expenses() if e["id"] == "e4")
check("receipt columns written", record["receipt_name"] == "bill.pdf" and record["receipt_ref"] == ref, record)
store.fetch_receipt.clear()
check("round trip matches", store.fetch_receipt(ref) == payload)

print("\n[7] replacing a bill removes the old chunks")
second = store.attach_receipt("e4", "bill2.pdf", "application/pdf", b"hello world")
check("new ref differs", second != ref)
check("old chunks gone", not [r for r in store._rows(store.CHUNKS_SHEET) if r[0] == ref])
store.fetch_receipt.clear()
check("new bill readable", store.fetch_receipt(second) == b"hello world")

print("\n[8] remove bill")
store.remove_receipt("e4")
record = next(e for e in store.load_expenses() if e["id"] == "e4")
check("receipt cleared", record["receipt_ref"] is None and record["receipt_name"] is None, record)
check("chunks cleared", store._rows(store.CHUNKS_SHEET) == [], store._rows(store.CHUNKS_SHEET))

print("\n[9] delete one expense")
store.attach_receipt("e3", "img.png", "image/png", b"\x89PNG-data")
store.delete_expense("e3")
ids = [e["id"] for e in store.load_expenses()]
check("row removed", "e3" not in ids, ids)
check("other rows intact", set(ids) == {"e1", "e2", "e4"}, ids)
check("its chunks removed", store._rows(store.CHUNKS_SHEET) == [])
check("header row survived", store._values(store.EXPENSES_SHEET)[0][0] == "id")

print("\n[10] rows stay addressable after a delete")
store.update_expense_details(
    {
        "id": "e4",
        "date": "2026-03-02",
        "category": "Labour",
        "phase": "Masonry",
        "description": "Brickwork final",
        "amount": 79000.0,
    }
)
after = {e["id"]: e for e in store.load_expenses()}
check("correct row edited", after["e4"]["description"] == "Brickwork final", after["e4"])
check("neighbours untouched", after["e1"]["description"] == "Cement OPC 53", after["e1"])

print("\n[11] clear all")
store.attach_receipt("e1", "a.pdf", "application/pdf", b"aaa")
store.clear_expenses()
check("no expenses", store.load_expenses() == [])
check("no chunks", store._rows(store.CHUNKS_SHEET) == [])
check("expenses header kept", store._values(store.EXPENSES_SHEET) == [store.EXPENSE_HEADER])
check("budgets untouched", store.load_budgets(DEFAULT_BUDGETS)["Material"] == 6000000.0)

print("\n[12] re-init after clear does not re-seed")
store._INITIALIZED_FOR = None
store.initialize_storage(SEED, DEFAULT_BUDGETS)
check("still empty", store.load_expenses() == [], store.load_expenses())

print("\n[13] tolerant parsing of hand-edited cells")
store._worksheet(store.EXPENSES_SHEET).append_rows(
    [["m1", "2026-04-01", "Material", "", "Manual row", "Rs 1,20,000", "", "", "", ""]]
)
store._invalidate(store.EXPENSES_SHEET)
manual = next(e for e in store.load_expenses() if e["id"] == "m1")
check("formatted amount parsed", manual["amount"] == 120000.0, manual)
check("blank phase defaults", manual["phase"] == "General", manual)

print("\n[14] OAuth2 user credentials (your own Google account)")
check("no oauth configured yet", store.oauth_user_info() is None)
os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "client-123.apps.googleusercontent.com"
os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "shh"
os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"] = "refresh-abc"
oauth_info = store.oauth_user_info()
check(
    "oauth_user_info reads env vars",
    oauth_info is not None
    and oauth_info["client_id"] == "client-123.apps.googleusercontent.com"
    and oauth_info["refresh_token"] == "refresh-abc"
    and oauth_info["token_uri"] == store.DEFAULT_OAUTH_TOKEN_URI,
    oauth_info,
)

store._SPREADSHEET = None
store._FINGERPRINT = None
store._connect()
check(
    "oauth takes precedence over a configured service account",
    store._FINGERPRINT is not None and store._FINGERPRINT.startswith("oauth:"),
    store._FINGERPRINT,
)

del os.environ["GOOGLE_OAUTH_CLIENT_ID"]
del os.environ["GOOGLE_OAUTH_CLIENT_SECRET"]
del os.environ["GOOGLE_OAUTH_REFRESH_TOKEN"]
store._SPREADSHEET = None
store._FINGERPRINT = None
store._connect()
check(
    "falls back to service account once oauth is unset",
    store._FINGERPRINT is not None and store._FINGERPRINT.startswith("service:"),
    store._FINGERPRINT,
)

print("\n[15] misconfiguration is reported clearly")
del os.environ["GSHEETS_SPREADSHEET_ID"]
store._SPREADSHEET = None
store._FINGERPRINT = None
try:
    store.initialize_storage(SEED, DEFAULT_BUDGETS)
    check("raises StorageConfigError", False, "no exception")
except store.StorageConfigError as exc:
    check("raises StorageConfigError", "No spreadsheet configured" in str(exc), str(exc))

print("\n" + ("ALL CHECKS PASSED" if not FAILURES else f"{len(FAILURES)} FAILURES: {FAILURES}"))
sys.exit(1 if FAILURES else 0)
