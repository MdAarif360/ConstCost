from __future__ import annotations

import html
import io
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


CATEGORIES = ["Labour", "Material", "ServiceCharge","Misc"]
PHASES = [
    "Foundation",
    "Compound Wall",
    "Structure",
    "Masonry",
    "Roofing",
    "Plumbing",
    "Electrical",
    "Finishing",
    "Interior",
    "Exterior",
    "General",
    "Other",
]

CURRENCY_SYMBOLS = {
    "INR": "Rs ",
}

CATEGORY_COLORS = {
    "Labour": "#059669",
    "Material": "#0284c7",
    "ServiceCharge": "#f95703",    
    "Misc": "#7c3aed",
}

DEFAULT_CATEGORY_BUDGETS = {
    "Labour": 5000000.0,
    "Material": 5000000.0,
    "ServiceCharge":1500000.0,
    "Misc": 250000.0,
}

BASE_DIR = Path(__file__).resolve().parent
CONFIGURED_DB_PATH = Path(
    os.getenv("COST_TRACKER_DB_PATH", "data/construction_cost_tracker.db")
)
DB_PATH = (
    CONFIGURED_DB_PATH
    if CONFIGURED_DB_PATH.is_absolute()
    else BASE_DIR / CONFIGURED_DB_PATH
)
DATABASE_URL_KEYS = ("DATABASE_URL", "database_url")
CONNECTION_SECRET_NAMES = (
    "construction_cost",
    "cost_tracker",
    "postgres",
    "postgresql",
    "sql",
)
_ENGINE: Engine | None = None
_ENGINE_URL: str | None = None

SEED_EXPENSES = [
    {
        "id": "e1",
        "date": "2026-01-15",
        "category": "Material",
        "phase": "Foundation",
        "description": "Cement (OPC 53 grade) - 200 bags",
        "amount": 110000.0,
    },
    {
        "id": "e2",
        "date": "2026-01-18",
        "category": "Labour",
        "phase": "Foundation",
        "description": "Excavation & foundation labour",
        "amount": 65000.0,
    },
    {
        "id": "e3",
        "date": "2026-01-25",
        "category": "Material",
        "phase": "Foundation",
        "description": "Steel reinforcement bars (TMT)",
        "amount": 185000.0,
    },
    {
        "id": "e4",
        "date": "2026-02-05",
        "category": "Labour",
        "phase": "Structure",
        "description": "Mason & helper wages - RCC work",
        "amount": 92000.0,
    },
    {
        "id": "e5",
        "date": "2026-02-12",
        "category": "Material",
        "phase": "Structure",
        "description": "Ready-mix concrete",
        "amount": 145000.0,
    },
    {
        "id": "e6",
        "date": "2026-02-28",
        "category": "Misc",
        "phase": "Structure",
        "description": "Equipment rental (mixer, vibrator)",
        "amount": 22000.0,
    },
    {
        "id": "e7",
        "date": "2026-03-10",
        "category": "Labour",
        "phase": "Masonry",
        "description": "Brickwork labour charges",
        "amount": 78000.0,
    },
    {
        "id": "e8",
        "date": "2026-03-15",
        "category": "Material",
        "phase": "Masonry",
        "description": "Bricks (12,000 nos)",
        "amount": 96000.0,
    },
    {
        "id": "e9",
        "date": "2026-03-20",
        "category": "Misc",
        "phase": "General",
        "description": "Municipal permits & approvals",
        "amount": 35000.0,
    },
    {
        "id": "e10",
        "date": "2026-04-05",
        "category": "Labour",
        "phase": "Roofing",
        "description": "Roofing/slab labour",
        "amount": 54000.0,
    },
    {
        "id": "e11",
        "date": "2026-04-12",
        "category": "Material",
        "phase": "Roofing",
        "description": "Waterproofing materials",
        "amount": 42000.0,
    },
    {
        "id": "e12",
        "date": "2026-04-25",
        "category": "Labour",
        "phase": "Plumbing & Electrical",
        "description": "Plumber & electrician wages",
        "amount": 68000.0,
    },
    {
        "id": "e13",
        "date": "2026-05-02",
        "category": "Material",
        "phase": "Plumbing & Electrical",
        "description": "Pipes, wires & fittings",
        "amount": 118000.0,
    },
    {
        "id": "e14",
        "date": "2026-05-18",
        "category": "Material",
        "phase": "Finishing",
        "description": "Tiles & flooring material",
        "amount": 165000.0,
    },
    {
        "id": "e15",
        "date": "2026-05-28",
        "category": "Labour",
        "phase": "Finishing",
        "description": "Tiling & plastering labour",
        "amount": 88000.0,
    },
    {
        "id": "e16",
        "date": "2026-06-08",
        "category": "Material",
        "phase": "Finishing",
        "description": "Paint & putty",
        "amount": 58000.0,
    },
    {
        "id": "e17",
        "date": "2026-06-15",
        "category": "Misc",
        "phase": "General",
        "description": "Site transportation & logistics",
        "amount": 28000.0,
    },
    {
        "id": "e18",
        "date": "2026-06-25",
        "category": "Labour",
        "phase": "Interior",
        "description": "Carpentry - doors & windows",
        "amount": 95000.0,
    },
    {
        "id": "e19",
        "date": "2026-07-02",
        "category": "Material",
        "phase": "Interior",
        "description": "Wood & hardware fittings",
        "amount": 132000.0,
    },
    {
        "id": "e20",
        "date": "2026-07-05",
        "category": "Misc",
        "phase": "General",
        "description": "Contingency / miscellaneous",
        "amount": 15000.0,
    },
]

CSV_TEMPLATE = (
    "Date,Category,Phase,Description,Amount\n"
    "2026-01-15,Material,Foundation,Cement - 50 bags,27500\n"
    "2026-01-18,Labour,Foundation,Excavation labour,15000\n"
    "2026-01-20,Misc,General,Site permit fee,5000\n"
)


def get_streamlit_secret(key: str) -> str | None:
    try:
        value = st.secrets.get(key)
    except Exception:
        return None
    return str(value).strip() if value else None


def get_streamlit_connection_url() -> str | None:
    try:
        connections = st.secrets.get("connections", {})
    except Exception:
        return None

    if not hasattr(connections, "get"):
        return None

    for name in CONNECTION_SECRET_NAMES:
        connection = connections.get(name)
        if hasattr(connection, "get"):
            value = connection.get("url")
            if value:
                return str(value).strip()

    return None


def configured_database_url() -> str | None:
    for key in DATABASE_URL_KEYS:
        value = os.getenv(key)
        if value:
            return value.strip()

    for key in DATABASE_URL_KEYS:
        value = get_streamlit_secret(key)
        if value:
            return value

    connection_url = get_streamlit_connection_url()
    if connection_url:
        return connection_url

    return None


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg2://{database_url.removeprefix('postgres://')}"
    if database_url.startswith("postgresql://"):
        return f"postgresql+psycopg2://{database_url.removeprefix('postgresql://')}"
    return database_url


def local_sqlite_url() -> str:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DB_PATH.as_posix()}"


def database_url() -> str:
    configured_url = configured_database_url()
    if configured_url:
        return normalize_database_url(configured_url)
    return local_sqlite_url()


def get_engine() -> Engine:
    global _ENGINE, _ENGINE_URL

    url = database_url()
    if _ENGINE is not None and _ENGINE_URL == url:
        return _ENGINE

    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite:"):
        kwargs["connect_args"] = {"check_same_thread": False}

    _ENGINE = create_engine(url, **kwargs)
    _ENGINE_URL = url
    return _ENGINE


def using_postgres() -> bool:
    return get_engine().url.get_backend_name().startswith("postgresql")


def database_storage_label() -> str:
    if using_postgres():
        return "PostgreSQL from DATABASE_URL"
    return f"SQLite at {DB_PATH}"


def normalize_receipt_bytes(value: Any) -> bytes | None:
    if value is None:
        return None
    if isinstance(value, memoryview):
        return value.tobytes()
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def initialize_database() -> None:
    amount_type = "DOUBLE PRECISION" if using_postgres() else "REAL"
    receipt_type = "BYTEA" if using_postgres() else "BLOB"

    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
            )
        )
        connection.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                amount {amount_type} NOT NULL
            )
            """
            )
        )
        connection.execute(
            text(
                f"""
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                phase TEXT NOT NULL,
                description TEXT NOT NULL,
                amount {amount_type} NOT NULL,
                receipt_name TEXT,
                receipt_type TEXT,
                receipt_bytes {receipt_type},
                created_at TEXT NOT NULL
            )
            """
            )
        )

        for category, amount in DEFAULT_CATEGORY_BUDGETS.items():
            connection.execute(
                text(
                    """
                    INSERT INTO budgets (category, amount)
                    VALUES (:category, :amount)
                    ON CONFLICT(category) DO NOTHING
                    """
                ),
                {"category": category, "amount": amount},
            )

        seeded = connection.execute(
            text("SELECT value FROM app_meta WHERE key = :key"),
            {"key": "seeded"},
        ).fetchone()
        if seeded is None:
            expense_count = connection.execute(
                text("SELECT COUNT(*) FROM expenses")
            ).scalar_one()
            if expense_count == 0:
                now = datetime.utcnow().isoformat()
                connection.execute(
                    text(
                        """
                    INSERT INTO expenses (
                        id, date, category, phase, description, amount,
                        receipt_name, receipt_type, receipt_bytes, created_at
                    )
                    VALUES (
                        :id, :date, :category, :phase, :description, :amount,
                        :receipt_name, :receipt_type, :receipt_bytes, :created_at
                    )
                    """
                    ),
                    [
                        {
                            "id": expense["id"],
                            "date": expense["date"],
                            "category": expense["category"],
                            "phase": expense["phase"],
                            "description": expense["description"],
                            "amount": float(expense["amount"]),
                            "receipt_name": None,
                            "receipt_type": None,
                            "receipt_bytes": None,
                            "created_at": now,
                        }
                        for expense in SEED_EXPENSES
                    ],
                )
            connection.execute(
                text(
                    """
                    INSERT INTO app_meta (key, value)
                    VALUES (:key, :value)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """
                ),
                {"key": "seeded", "value": "1"},
            )


def load_expenses_from_db() -> list[dict[str, Any]]:
    with get_engine().connect() as connection:
        rows = connection.execute(
            text(
                """
            SELECT
                id, date, category, phase, description, amount,
                receipt_name, receipt_type, receipt_bytes
            FROM expenses
            ORDER BY date DESC, created_at DESC, id DESC
            """
            )
        ).mappings().all()

    expenses = []
    for row in rows:
        expense = dict(row)
        expense["receipt_bytes"] = normalize_receipt_bytes(expense.get("receipt_bytes"))
        expenses.append(expense)
    return expenses


def load_budgets_from_db() -> dict[str, float]:
    budgets = dict(DEFAULT_CATEGORY_BUDGETS)
    with get_engine().connect() as connection:
        rows = connection.execute(
            text("SELECT category, amount FROM budgets")
        ).mappings().all()
    for row in rows:
        if row["category"] in budgets:
            budgets[row["category"]] = float(row["amount"])
    return budgets


def save_budget_to_db(category: str, amount: float) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
            INSERT INTO budgets (category, amount)
            VALUES (:category, :amount)
            ON CONFLICT(category) DO UPDATE SET amount = excluded.amount
            """
            ),
            {"category": category, "amount": float(amount)},
        )


def save_expense_to_db(expense: dict[str, Any]) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
            INSERT INTO expenses (
                id, date, category, phase, description, amount,
                receipt_name, receipt_type, receipt_bytes, created_at
            )
            VALUES (
                :id, :date, :category, :phase, :description, :amount,
                :receipt_name, :receipt_type, :receipt_bytes, :created_at
            )
            ON CONFLICT(id) DO UPDATE SET
                date = excluded.date,
                category = excluded.category,
                phase = excluded.phase,
                description = excluded.description,
                amount = excluded.amount,
                receipt_name = excluded.receipt_name,
                receipt_type = excluded.receipt_type,
                receipt_bytes = excluded.receipt_bytes
            """
            ),
            {
                "id": expense["id"],
                "date": expense["date"],
                "category": expense["category"],
                "phase": expense["phase"],
                "description": expense["description"],
                "amount": float(expense["amount"]),
                "receipt_name": expense.get("receipt_name"),
                "receipt_type": expense.get("receipt_type"),
                "receipt_bytes": expense.get("receipt_bytes"),
                "created_at": datetime.utcnow().isoformat(),
            },
        )


def save_expenses_to_db(expenses: list[dict[str, Any]]) -> None:
    if not expenses:
        return
    now = datetime.utcnow().isoformat()
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
            INSERT INTO expenses (
                id, date, category, phase, description, amount,
                receipt_name, receipt_type, receipt_bytes, created_at
            )
            VALUES (
                :id, :date, :category, :phase, :description, :amount,
                :receipt_name, :receipt_type, :receipt_bytes, :created_at
            )
            ON CONFLICT(id) DO UPDATE SET
                date = excluded.date,
                category = excluded.category,
                phase = excluded.phase,
                description = excluded.description,
                amount = excluded.amount,
                receipt_name = excluded.receipt_name,
                receipt_type = excluded.receipt_type,
                receipt_bytes = excluded.receipt_bytes
            """
            ),
            [
                {
                    "id": expense["id"],
                    "date": expense["date"],
                    "category": expense["category"],
                    "phase": expense["phase"],
                    "description": expense["description"],
                    "amount": float(expense["amount"]),
                    "receipt_name": expense.get("receipt_name"),
                    "receipt_type": expense.get("receipt_type"),
                    "receipt_bytes": expense.get("receipt_bytes"),
                    "created_at": now,
                }
                for expense in expenses
            ],
        )


def update_expense_details_in_db(expense: dict[str, Any]) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
                UPDATE expenses
                SET
                    date = :date,
                    category = :category,
                    phase = :phase,
                    description = :description,
                    amount = :amount
                WHERE id = :id
                """
            ),
            {
                "id": expense["id"],
                "date": expense["date"],
                "category": expense["category"],
                "phase": expense["phase"],
                "description": expense["description"],
                "amount": float(expense["amount"]),
            },
        )


def delete_expense_from_db(expense_id: str) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text("DELETE FROM expenses WHERE id = :expense_id"),
            {"expense_id": expense_id},
        )


def clear_expenses_from_db() -> None:
    with get_engine().begin() as connection:
        connection.execute(text("DELETE FROM expenses"))


def update_receipt_in_db(
    expense_id: str,
    receipt_name: str,
    receipt_type: str,
    receipt_bytes: bytes,
) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
            UPDATE expenses
            SET receipt_name = :receipt_name,
                receipt_type = :receipt_type,
                receipt_bytes = :receipt_bytes
            WHERE id = :expense_id
            """
            ),
            {
                "receipt_name": receipt_name,
                "receipt_type": receipt_type,
                "receipt_bytes": receipt_bytes,
                "expense_id": expense_id,
            },
        )


def remove_receipt_from_db(expense_id: str) -> None:
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """
            UPDATE expenses
            SET receipt_name = NULL, receipt_type = NULL, receipt_bytes = NULL
            WHERE id = :expense_id
            """
            ),
            {"expense_id": expense_id},
        )


def init_state() -> None:
    initialize_database()
    st.session_state.expenses = load_expenses_from_db()
    st.session_state.category_budgets = load_budgets_from_db()
    if "currency_code" not in st.session_state:
        st.session_state.currency_code = "INR"
    if "clear_confirm" not in st.session_state:
        st.session_state.clear_confirm = False
    if "add_form_version" not in st.session_state:
        st.session_state.add_form_version = 0
    if "csv_form_version" not in st.session_state:
        st.session_state.csv_form_version = 0
    if "receipt_upload_versions" not in st.session_state:
        st.session_state.receipt_upload_versions = {}
    if "last_import_result" not in st.session_state:
        st.session_state.last_import_result = None
    if "editing_expense_id" not in st.session_state:
        st.session_state.editing_expense_id = None
    if "edit_form_version" not in st.session_state:
        st.session_state.edit_form_version = 0


def indian_grouped(value: float) -> str:
    rounded = int(round(abs(value)))
    digits = str(rounded)
    if len(digits) <= 3:
        grouped = digits
    else:
        head = digits[:-3]
        tail = digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts + [tail])
    return f"-{grouped}" if value < 0 else grouped


def format_money(value: float) -> str:
    symbol = CURRENCY_SYMBOLS[st.session_state.currency_code]
    return f"{symbol}{indian_grouped(value)}"


def normalize_category(raw: str) -> str | None:
    value = str(raw).strip().lower()
    if value.startswith("labo"):
        return "Labour"
    if value.startswith("mat"):
        return "Material"
    if value.startswith("misc") or value.startswith("other"):
        return "Misc"
    return None


def parse_amount(raw: Any) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", str(raw))
    if cleaned in {"", ".", "-", "-."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(raw: Any) -> str | None:
    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date().isoformat()


def expense_date_for_input(raw: Any) -> date:
    parsed = pd.to_datetime(raw, errors="coerce")
    if pd.isna(parsed):
        return date.today()
    return parsed.date()


def get_expenses_frame() -> pd.DataFrame:
    columns = [
        "id",
        "date",
        "category",
        "phase",
        "description",
        "amount",
        "receipt_name",
        "receipt_type",
        "receipt_bytes",
    ]
    if not st.session_state.expenses:
        return pd.DataFrame(columns=columns + ["date_value"])

    frame = pd.DataFrame(st.session_state.expenses)
    for column in columns:
        if column not in frame.columns:
            frame[column] = None
    for column in ["receipt_name", "receipt_type", "receipt_bytes"]:
        frame[column] = frame[column].where(frame[column].notna(), None)
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce").fillna(0.0)
    frame["date_value"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame


def totals_by_category(frame: pd.DataFrame) -> dict[str, float]:
    totals = {category: 0.0 for category in CATEGORIES}
    if not frame.empty:
        grouped = frame.groupby("category")["amount"].sum()
        for category, amount in grouped.items():
            if category in totals:
                totals[category] = float(amount)
    return totals


def total_budget() -> float:
    return sum(float(st.session_state.category_budgets[category]) for category in CATEGORIES)


def append_expense(expense: dict[str, Any]) -> None:
    save_expense_to_db(expense)
    st.session_state.expenses = [expense] + st.session_state.expenses
    st.session_state.clear_confirm = False


def update_expense_details(expense: dict[str, Any]) -> None:
    update_expense_details_in_db(expense)
    st.session_state.expenses = load_expenses_from_db()
    st.session_state.editing_expense_id = None
    st.session_state.edit_form_version += 1
    st.session_state.clear_confirm = False


def delete_expense(expense_id: str) -> None:
    delete_expense_from_db(expense_id)
    st.session_state.expenses = [
        expense for expense in st.session_state.expenses if expense["id"] != expense_id
    ]
    st.session_state.receipt_upload_versions.pop(expense_id, None)
    if st.session_state.editing_expense_id == expense_id:
        st.session_state.editing_expense_id = None


def update_expense_receipt(expense_id: str, uploaded_file: Any) -> None:
    receipt_bytes = uploaded_file.getvalue()
    receipt_type = uploaded_file.type or "application/octet-stream"
    update_receipt_in_db(expense_id, uploaded_file.name, receipt_type, receipt_bytes)
    for expense in st.session_state.expenses:
        if expense["id"] == expense_id:
            expense["receipt_name"] = uploaded_file.name
            expense["receipt_type"] = receipt_type
            expense["receipt_bytes"] = receipt_bytes
            break


def remove_expense_receipt(expense_id: str) -> None:
    remove_receipt_from_db(expense_id)
    for expense in st.session_state.expenses:
        if expense["id"] == expense_id:
            expense.pop("receipt_name", None)
            expense.pop("receipt_type", None)
            expense.pop("receipt_bytes", None)
            break


def export_csv() -> bytes:
    rows = []
    for expense in sorted(st.session_state.expenses, key=lambda item: item["date"]):
        rows.append(
            {
                "Date": expense["date"],
                "Category": expense["category"],
                "Phase": expense["phase"],
                "Description": expense["description"],
                "Amount": expense["amount"],
            }
        )
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def import_expenses_from_csv(uploaded_file: Any) -> tuple[int, int, list[str]]:
    try:
        frame = pd.read_csv(io.BytesIO(uploaded_file.getvalue()))
    except Exception as exc:
        return 0, 0, [f"Could not parse CSV: {exc}"]

    lookup = {str(column).strip().lower(): column for column in frame.columns}

    def cell(row: pd.Series, name: str, fallback: str = "") -> str:
        column = lookup.get(name.lower())
        if column is None:
            return fallback
        value = row[column]
        if pd.isna(value):
            return fallback
        return str(value).strip()

    imported: list[dict[str, Any]] = []
    reasons: list[str] = []

    for index, row in frame.iterrows():
        row_num = int(index) + 2
        raw_date = cell(row, "date")
        raw_category = cell(row, "category")
        raw_phase = cell(row, "phase", "General")
        raw_description = cell(row, "description")
        raw_amount = cell(row, "amount")

        if not raw_date or not raw_category or not raw_description or not raw_amount:
            reasons.append(f"Row {row_num}: missing required field(s), skipped.")
            continue

        category = normalize_category(raw_category)
        if category is None:
            reasons.append(
                f'Row {row_num}: unrecognized category "{raw_category}", skipped.'
            )
            continue

        amount = parse_amount(raw_amount)
        if amount is None or amount <= 0:
            reasons.append(f'Row {row_num}: invalid amount "{raw_amount}", skipped.')
            continue

        date_value = parse_date(raw_date)
        if date_value is None:
            reasons.append(f'Row {row_num}: invalid date "{raw_date}", skipped.')
            continue

        imported.append(
            {
                "id": f"e{uuid.uuid4().hex}",
                "date": date_value,
                "category": category,
                "phase": raw_phase or "General",
                "description": raw_description,
                "amount": amount,
            }
        )

    if imported:
        save_expenses_to_db(imported)
        st.session_state.expenses = load_expenses_from_db()

    return len(imported), len(reasons), reasons[:8]


def status_class(percent: float) -> str:
    if percent >= 100:
        return "danger"
    if percent >= 85:
        return "warn"
    return "good"


def money_axis(value: float) -> str:
    return format_money(float(value))


def apply_page_styles() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                padding-top: 2rem;
                padding-bottom: 3rem;
                max-width: 1180px;
            }
            .summary-metric-card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 1rem;
                box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
                min-height: 122px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }
            .summary-metric-label {
                color: #64748b;
                font-size: 1rem;
                line-height: 1.25;
                margin-bottom: 0.9rem;
            }
            .summary-metric-value {
                color: #0f172a;
                font-size: clamp(1.65rem, 2.15vw, 2.28rem);
                font-weight: 500;
                line-height: 1.1;
                letter-spacing: 0;
                white-space: nowrap;
            }
            .section-title {
                margin: 1.5rem 0 0.75rem;
                font-size: 1.1rem;
                font-weight: 700;
                color: #0f172a;
            }
            .category-chip {
                display: inline-block;
                border-radius: 999px;
                padding: 0.18rem 0.55rem;
                font-size: 0.78rem;
                font-weight: 700;
                border: 1px solid transparent;
            }
            .chip-Labour {
                color: #047857;
                background: #d1fae5;
                border-color: #a7f3d0;
            }
            .chip-Material {
                color: #0369a1;
                background: #e0f2fe;
                border-color: #bae6fd;
            }
            .chip-Misc {
                color: #6d28d9;
                background: #ede9fe;
                border-color: #ddd6fe;
            }
            .muted {
                color: #64748b;
                font-size: 0.88rem;
            }
            .amount {
                font-size: 1.05rem;
                font-weight: 800;
                text-align: right;
                color: #0f172a;
            }
            .good {
                color: #059669;
                font-weight: 800;
            }
            .warn {
                color: #d97706;
                font-weight: 800;
            }
            .danger {
                color: #dc2626;
                font-weight: 800;
            }
            .receipt-label {
                color: #4338ca;
                font-size: 0.86rem;
                font-weight: 700;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_summary_metric(column: Any, label: str, value: str) -> None:
    column.markdown(
        (
            '<div class="summary-metric-card">'
            f'<div class="summary-metric-label">{html.escape(label)}</div>'
            f'<div class="summary-metric-value">{html.escape(value)}</div>'
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_header() -> None:
    left, right = st.columns([0.72, 0.28], vertical_alignment="center")
    with left:
        st.title("Construction Cost Tracker")
        st.caption("Track labour, material, and miscellaneous spending against budget.")
    with right:
        currency_codes = list(CURRENCY_SYMBOLS)
        current_index = currency_codes.index(st.session_state.currency_code)
        st.session_state.currency_code = st.selectbox(
            "Currency",
            currency_codes,
            index=current_index,
            format_func=lambda code: f"{code} ({CURRENCY_SYMBOLS[code].strip()})",
        )


def render_summary(frame: pd.DataFrame, category_totals: dict[str, float]) -> None:
    spent = float(frame["amount"].sum()) if not frame.empty else 0.0
    budget = total_budget()
    remaining = budget - spent
    percent_used = (spent / budget * 100) if budget > 0 else 0.0
    bills_attached = int(frame["receipt_name"].notna().sum()) if not frame.empty else 0

    cols = st.columns(4)
    render_summary_metric(cols[0], "Total Budget", format_money(budget))
    render_summary_metric(cols[1], "Total Spent", format_money(spent))
    render_summary_metric(cols[2], "Remaining", format_money(remaining))
    render_summary_metric(cols[3], "Bills Attached", f"{bills_attached} / {len(frame)}")

    st.markdown('<div class="section-title">Budget Used</div>', unsafe_allow_html=True)
    st.markdown(
        f'<span class="{status_class(percent_used)}">{percent_used:.1f}%</span>',
        unsafe_allow_html=True,
    )
    st.progress(min(max(percent_used / 100, 0.0), 1.0))

    st.markdown(
        '<div class="section-title">Budget by Category</div>',
        unsafe_allow_html=True,
    )
    budget_cols = st.columns(3)
    for column, category in zip(budget_cols, CATEGORIES):
        with column:
            spent_for_category = category_totals[category]
            current_budget = float(st.session_state.category_budgets[category])
            new_budget = st.number_input(
                f"{category} budget",
                min_value=0.0,
                value=current_budget,
                step=10000.0,
                key=f"budget_input_{category}",
            )
            new_budget = float(new_budget)
            if new_budget != current_budget:
                save_budget_to_db(category, new_budget)
            st.session_state.category_budgets[category] = new_budget
            percent = (
                spent_for_category / new_budget * 100 if new_budget > 0 else 0.0
            )
            st.markdown(
                f"**{category}**  \n"
                f"{format_money(spent_for_category)} / {format_money(float(new_budget))}"
            )
            st.progress(min(max(percent / 100, 0.0), 1.0))
            st.markdown(
                f'<span class="{status_class(percent)}">{percent:.1f}% used</span>',
                unsafe_allow_html=True,
            )


def render_charts(frame: pd.DataFrame, category_totals: dict[str, float]) -> None:
    st.markdown('<div class="section-title">Dashboard</div>', unsafe_allow_html=True)
    if frame.empty:
        st.info("No data available.")
        return

    pie_frame = pd.DataFrame(
        [
            {"Category": category, "Amount": amount}
            for category, amount in category_totals.items()
            if amount > 0
        ]
    )
    phase_frame = (
        frame.groupby("phase", as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=True)
    )

    chart_left, chart_right = st.columns(2)
    with chart_left:
        st.subheader("Spend by Category")
        if pie_frame.empty:
            st.info("No data available.")
        else:
            fig = px.pie(
                pie_frame,
                names="Category",
                values="Amount",
                hole=0.45,
                color="Category",
                color_discrete_map=CATEGORY_COLORS,
            )
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=340)
            st.plotly_chart(fig, use_container_width=True)

    with chart_right:
        st.subheader("Spend by Phase")
        if phase_frame.empty:
            st.info("No data available.")
        else:
            fig = px.bar(
                phase_frame,
                x="amount",
                y="phase",
                orientation="h",
                labels={"amount": "Spend", "phase": "Phase"},
                color="phase",
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(
                showlegend=False,
                margin=dict(l=10, r=10, t=20, b=10),
                height=340,
                xaxis_tickprefix=CURRENCY_SYMBOLS[st.session_state.currency_code],
            )
            fig.update_xaxes(tickformat=",")
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Monthly Spend Trend")
    monthly_source = frame.dropna(subset=["date_value"]).copy()
    if monthly_source.empty:
        st.info("No dated expenses available.")
        return

    monthly_source["month"] = monthly_source["date_value"].dt.to_period("M").dt.to_timestamp()
    monthly_frame = (
        monthly_source.pivot_table(
            index="month",
            columns="category",
            values="amount",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reset_index()
        .sort_values("month")
    )
    for category in CATEGORIES:
        if category not in monthly_frame.columns:
            monthly_frame[category] = 0.0

    fig = px.line(
        monthly_frame,
        x="month",
        y=CATEGORIES,
        markers=True,
        labels={"value": "Spend", "month": "Month", "variable": "Category"},
        color_discrete_map=CATEGORY_COLORS,
    )
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=350)
    fig.update_yaxes(tickformat=",")
    st.plotly_chart(fig, use_container_width=True)


def render_import_export() -> None:
    st.markdown(
        '<div class="section-title">Import and Export</div>',
        unsafe_allow_html=True,
    )
    import_col, export_col = st.columns([0.62, 0.38])

    with import_col:
        if st.session_state.last_import_result:
            result = st.session_state.last_import_result
            if result["imported"]:
                st.success(f"Imported {result['imported']} row(s).")
            if result["skipped"]:
                st.warning(f"Skipped {result['skipped']} row(s).")
                for reason in result["reasons"]:
                    st.caption(reason)

        with st.form(f"csv_import_form_{st.session_state.csv_form_version}"):
            uploaded_csv = st.file_uploader(
                "CSV file",
                type=["csv"],
                help="Required columns: Date, Category, Phase, Description, Amount.",
            )
            submitted = st.form_submit_button("Import CSV")

        if submitted:
            if uploaded_csv is None:
                st.warning("Choose a CSV file before importing.")
            else:
                imported, skipped, reasons = import_expenses_from_csv(uploaded_csv)
                st.session_state.last_import_result = {
                    "imported": imported,
                    "skipped": skipped,
                    "reasons": reasons,
                }
                st.session_state.editing_expense_id = None
                st.session_state.edit_form_version += 1
                st.session_state.csv_form_version += 1
                st.rerun()

    with export_col:
        st.download_button(
            "Download CSV",
            data=export_csv(),
            file_name="construction_cost_tracker.csv",
            mime="text/csv",
            use_container_width=True,
        )
        st.download_button(
            "Download Template",
            data=CSV_TEMPLATE.encode("utf-8"),
            file_name="expense_import_template.csv",
            mime="text/csv",
            use_container_width=True,
        )


def render_add_expense_form() -> None:
    st.markdown('<div class="section-title">Add Expense</div>', unsafe_allow_html=True)
    form_key = st.session_state.add_form_version
    with st.form(f"add_expense_form_{form_key}"):
        col1, col2, col3, col4 = st.columns(4)
        expense_date = col1.date_input("Date", value=date.today())
        category = col2.selectbox("Category", CATEGORIES, index=1)
        phase = col3.selectbox("Phase", PHASES)
        amount = col4.number_input("Amount", min_value=0.0, step=1000.0)
        description = st.text_input("Description", placeholder="Cement - 50 bags")
        receipt = st.file_uploader(
            "Bill / invoice (optional)",
            type=["png", "jpg", "jpeg", "gif", "webp", "pdf"],
        )
        submitted = st.form_submit_button("Add Expense")

    if not submitted:
        return

    if not description.strip():
        st.error("Please add a description.")
        return
    if amount <= 0:
        st.error("Please enter an amount greater than 0.")
        return

    new_expense: dict[str, Any] = {
        "id": f"e{uuid.uuid4().hex}",
        "date": expense_date.isoformat(),
        "category": category,
        "phase": phase,
        "description": description.strip(),
        "amount": float(amount),
    }
    if receipt is not None:
        new_expense["receipt_name"] = receipt.name
        new_expense["receipt_type"] = receipt.type or "application/octet-stream"
        new_expense["receipt_bytes"] = receipt.getvalue()

    append_expense(new_expense)
    st.session_state.add_form_version += 1
    st.success("Expense added.")
    st.rerun()


def render_edit_expense_form(expense: dict[str, Any]) -> None:
    expense_id = str(expense["id"])
    st.markdown("**Edit expense**")
    form_key = f"edit_expense_form_{expense_id}_{st.session_state.edit_form_version}"

    category_value = str(expense.get("category", CATEGORIES[0]))
    phase_value = str(expense.get("phase", PHASES[0]))
    category_index = CATEGORIES.index(category_value) if category_value in CATEGORIES else 0
    phase_index = PHASES.index(phase_value) if phase_value in PHASES else 0

    with st.form(form_key):
        col1, col2, col3, col4 = st.columns(4)
        edited_date = col1.date_input(
            "Date",
            value=expense_date_for_input(expense.get("date")),
            key=f"edit_date_{expense_id}",
        )
        edited_category = col2.selectbox(
            "Category",
            CATEGORIES,
            index=category_index,
            key=f"edit_category_{expense_id}",
        )
        edited_phase = col3.selectbox(
            "Phase",
            PHASES,
            index=phase_index,
            key=f"edit_phase_{expense_id}",
        )
        edited_amount = col4.number_input(
            "Amount",
            min_value=0.0,
            value=float(expense.get("amount") or 0.0),
            step=1000.0,
            key=f"edit_amount_{expense_id}",
        )
        edited_description = st.text_input(
            "Description",
            value=str(expense.get("description") or ""),
            key=f"edit_description_{expense_id}",
        )
        save_col, cancel_col = st.columns(2)
        with save_col:
            save_submitted = st.form_submit_button(
                "Save changes",
                type="primary",
                use_container_width=True,
            )
        with cancel_col:
            cancel_submitted = st.form_submit_button(
                "Cancel",
                use_container_width=True,
            )

    if cancel_submitted:
        st.session_state.editing_expense_id = None
        st.session_state.edit_form_version += 1
        st.rerun()

    if not save_submitted:
        return

    if not edited_description.strip():
        st.error("Please add a description.")
        return
    if edited_amount <= 0:
        st.error("Please enter an amount greater than 0.")
        return

    updated_expense = dict(expense)
    updated_expense.update(
        {
            "date": edited_date.isoformat(),
            "category": edited_category,
            "phase": edited_phase,
            "description": edited_description.strip(),
            "amount": float(edited_amount),
        }
    )
    update_expense_details(updated_expense)
    st.success("Expense updated.")
    st.rerun()


def render_receipt_controls(expense: dict[str, Any]) -> None:
    expense_id = expense["id"]
    receipt_name = expense.get("receipt_name")
    receipt_bytes = expense.get("receipt_bytes")
    receipt_type = expense.get("receipt_type") or "application/octet-stream"

    if receipt_name and receipt_bytes:
        st.markdown(
            f'<span class="receipt-label">{html.escape(str(receipt_name))}</span>',
            unsafe_allow_html=True,
        )
        st.download_button(
            "Download bill",
            data=receipt_bytes,
            file_name=receipt_name,
            mime=receipt_type,
            key=f"download_{expense_id}",
            use_container_width=True,
        )
        if str(receipt_type).startswith("image/"):
            with st.expander("Preview"):
                st.image(receipt_bytes, use_container_width=True)
        if st.button("Remove bill", key=f"remove_receipt_{expense_id}", use_container_width=True):
            remove_expense_receipt(expense_id)
            st.rerun()
        return

    version = st.session_state.receipt_upload_versions.get(expense_id, 0)
    uploaded_receipt = st.file_uploader(
        "Attach bill / invoice",
        type=["png", "jpg", "jpeg", "gif", "webp", "pdf"],
        key=f"receipt_upload_{expense_id}_{version}",
        label_visibility="collapsed",
    )
    if uploaded_receipt is not None:
        update_expense_receipt(expense_id, uploaded_receipt)
        st.session_state.receipt_upload_versions[expense_id] = version + 1
        st.rerun()


def render_expense_log(frame: pd.DataFrame) -> None:
    st.markdown('<div class="section-title">Expense Log</div>', unsafe_allow_html=True)
    tools_left, tools_right = st.columns([0.35, 0.65], vertical_alignment="bottom")
    selected_category = tools_left.selectbox("Filter", ["All"] + CATEGORIES)

    with tools_right:
        if st.session_state.clear_confirm:
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("Confirm clear all data", type="primary", use_container_width=True):
                clear_expenses_from_db()
                st.session_state.expenses = []
                st.session_state.clear_confirm = False
                st.session_state.receipt_upload_versions = {}
                st.session_state.editing_expense_id = None
                st.session_state.edit_form_version += 1
                st.rerun()
            if cancel_col.button("Cancel", use_container_width=True):
                st.session_state.clear_confirm = False
                st.rerun()
        elif st.button("Clear all data", use_container_width=True):
            st.session_state.clear_confirm = True
            st.rerun()

    display_frame = frame.copy()
    if selected_category != "All":
        display_frame = display_frame[display_frame["category"] == selected_category]
    display_frame = display_frame.sort_values(
        by=["date_value", "id"], ascending=[False, False], na_position="last"
    )

    if display_frame.empty:
        st.info("No data available.")
        return

    st.caption(f"{len(display_frame)} expense(s)")
    for expense in display_frame.to_dict("records"):
        expense_id = str(expense["id"])
        is_editing = st.session_state.editing_expense_id == expense_id
        with st.container(border=True):
            if is_editing:
                render_edit_expense_form(expense)
                receipt_col, actions_col = st.columns([0.72, 0.28])
                with receipt_col:
                    render_receipt_controls(expense)
                with actions_col:
                    if st.button(
                        "Delete",
                        key=f"delete_editing_{expense_id}",
                        use_container_width=True,
                    ):
                        delete_expense(expense_id)
                        st.rerun()
                continue

            detail_col, amount_col, receipt_col, actions_col = st.columns(
                [0.46, 0.16, 0.22, 0.16],
                vertical_alignment="center",
            )
            category = str(expense["category"])
            with detail_col:
                st.markdown(
                    f'<span class="category-chip chip-{html.escape(category)}">'
                    f"{html.escape(category)}</span> "
                    f'<span class="muted">{html.escape(str(expense["phase"]))}</span>',
                    unsafe_allow_html=True,
                )
                st.markdown(f"**{html.escape(str(expense['description']))}**")
                st.caption(str(expense["date"]))
            with amount_col:
                st.markdown(
                    f'<div class="amount">{format_money(float(expense["amount"]))}</div>',
                    unsafe_allow_html=True,
                )
            with receipt_col:
                render_receipt_controls(expense)
            with actions_col:
                if st.button("Edit", key=f"edit_{expense_id}", use_container_width=True):
                    st.session_state.editing_expense_id = expense_id
                    st.session_state.edit_form_version += 1
                    st.rerun()
                if st.button("Delete", key=f"delete_{expense_id}", use_container_width=True):
                    delete_expense(expense_id)
                    st.rerun()

    st.caption(
        f"Expenses, budgets, and attached bills are saved in {database_storage_label()}."
    )


def main() -> None:
    st.set_page_config(page_title="Construction Cost Tracker", layout="wide")
    init_state()
    apply_page_styles()

    render_header()
    frame = get_expenses_frame()
    category_totals = totals_by_category(frame)
    render_summary(frame, category_totals)

    dashboard_tab, manage_tab = st.tabs(["Dashboard", "Manage Expenses"])
    with dashboard_tab:
        render_charts(frame, category_totals)
    with manage_tab:
        render_import_export()
        render_add_expense_form()
        render_expense_log(get_expenses_frame())


if __name__ == "__main__":
    main()
