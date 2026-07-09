from __future__ import annotations

import html
import io
import os
import re
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st


CATEGORIES = ["Labour", "Material", "Misc"]
PHASES = [
    "Foundation",
    "Structure",
    "Masonry",
    "Roofing",
    "Plumbing & Electrical",
    "Finishing",
    "Interior",
    "Exterior",
    "General",
    "Other",
]

CURRENCY_SYMBOLS = {
    "INR": "Rs ",
    "USD": "$",
    "EUR": "EUR ",
    "GBP": "GBP ",
}

CATEGORY_COLORS = {
    "Labour": "#059669",
    "Material": "#0284c7",
    "Misc": "#7c3aed",
}

DEFAULT_CATEGORY_BUDGETS = {
    "Labour": 900000.0,
    "Material": 1400000.0,
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


@contextmanager
def connect_db() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    with connect_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS budgets (
                category TEXT PRIMARY KEY,
                amount REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                phase TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                receipt_name TEXT,
                receipt_type TEXT,
                receipt_bytes BLOB,
                created_at TEXT NOT NULL
            )
            """
        )

        for category, amount in DEFAULT_CATEGORY_BUDGETS.items():
            connection.execute(
                "INSERT OR IGNORE INTO budgets (category, amount) VALUES (?, ?)",
                (category, amount),
            )

        seeded = connection.execute(
            "SELECT value FROM app_meta WHERE key = 'seeded'"
        ).fetchone()
        if seeded is None:
            expense_count = connection.execute(
                "SELECT COUNT(*) FROM expenses"
            ).fetchone()[0]
            if expense_count == 0:
                now = datetime.utcnow().isoformat()
                connection.executemany(
                    """
                    INSERT INTO expenses (
                        id, date, category, phase, description, amount,
                        receipt_name, receipt_type, receipt_bytes, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            expense["id"],
                            expense["date"],
                            expense["category"],
                            expense["phase"],
                            expense["description"],
                            float(expense["amount"]),
                            None,
                            None,
                            None,
                            now,
                        )
                        for expense in SEED_EXPENSES
                    ],
                )
            connection.execute(
                "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('seeded', '1')"
            )


def load_expenses_from_db() -> list[dict[str, Any]]:
    with connect_db() as connection:
        rows = connection.execute(
            """
            SELECT
                id, date, category, phase, description, amount,
                receipt_name, receipt_type, receipt_bytes
            FROM expenses
            ORDER BY date DESC, created_at DESC, id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def load_budgets_from_db() -> dict[str, float]:
    budgets = dict(DEFAULT_CATEGORY_BUDGETS)
    with connect_db() as connection:
        rows = connection.execute("SELECT category, amount FROM budgets").fetchall()
    for row in rows:
        if row["category"] in budgets:
            budgets[row["category"]] = float(row["amount"])
    return budgets


def save_budget_to_db(category: str, amount: float) -> None:
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO budgets (category, amount)
            VALUES (?, ?)
            ON CONFLICT(category) DO UPDATE SET amount = excluded.amount
            """,
            (category, float(amount)),
        )


def save_expense_to_db(expense: dict[str, Any]) -> None:
    with connect_db() as connection:
        connection.execute(
            """
            INSERT INTO expenses (
                id, date, category, phase, description, amount,
                receipt_name, receipt_type, receipt_bytes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                date = excluded.date,
                category = excluded.category,
                phase = excluded.phase,
                description = excluded.description,
                amount = excluded.amount,
                receipt_name = excluded.receipt_name,
                receipt_type = excluded.receipt_type,
                receipt_bytes = excluded.receipt_bytes
            """,
            (
                expense["id"],
                expense["date"],
                expense["category"],
                expense["phase"],
                expense["description"],
                float(expense["amount"]),
                expense.get("receipt_name"),
                expense.get("receipt_type"),
                expense.get("receipt_bytes"),
                datetime.utcnow().isoformat(),
            ),
        )


def save_expenses_to_db(expenses: list[dict[str, Any]]) -> None:
    if not expenses:
        return
    now = datetime.utcnow().isoformat()
    with connect_db() as connection:
        connection.executemany(
            """
            INSERT INTO expenses (
                id, date, category, phase, description, amount,
                receipt_name, receipt_type, receipt_bytes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                date = excluded.date,
                category = excluded.category,
                phase = excluded.phase,
                description = excluded.description,
                amount = excluded.amount,
                receipt_name = excluded.receipt_name,
                receipt_type = excluded.receipt_type,
                receipt_bytes = excluded.receipt_bytes
            """,
            [
                (
                    expense["id"],
                    expense["date"],
                    expense["category"],
                    expense["phase"],
                    expense["description"],
                    float(expense["amount"]),
                    expense.get("receipt_name"),
                    expense.get("receipt_type"),
                    expense.get("receipt_bytes"),
                    now,
                )
                for expense in expenses
            ],
        )


def delete_expense_from_db(expense_id: str) -> None:
    with connect_db() as connection:
        connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))


def clear_expenses_from_db() -> None:
    with connect_db() as connection:
        connection.execute("DELETE FROM expenses")


def update_receipt_in_db(
    expense_id: str,
    receipt_name: str,
    receipt_type: str,
    receipt_bytes: bytes,
) -> None:
    with connect_db() as connection:
        connection.execute(
            """
            UPDATE expenses
            SET receipt_name = ?, receipt_type = ?, receipt_bytes = ?
            WHERE id = ?
            """,
            (receipt_name, receipt_type, receipt_bytes, expense_id),
        )


def remove_receipt_from_db(expense_id: str) -> None:
    with connect_db() as connection:
        connection.execute(
            """
            UPDATE expenses
            SET receipt_name = NULL, receipt_type = NULL, receipt_bytes = NULL
            WHERE id = ?
            """,
            (expense_id,),
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


def delete_expense(expense_id: str) -> None:
    delete_expense_from_db(expense_id)
    st.session_state.expenses = [
        expense for expense in st.session_state.expenses if expense["id"] != expense_id
    ]
    st.session_state.receipt_upload_versions.pop(expense_id, None)


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
            div[data-testid="stMetric"] {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 1rem;
                box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            }
            div[data-testid="stMetric"] label {
                color: #64748b;
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
    cols[0].metric("Total Budget", format_money(budget))
    cols[1].metric("Total Spent", format_money(spent))
    cols[2].metric("Remaining", format_money(remaining))
    cols[3].metric("Bills Attached", f"{bills_attached} / {len(frame)}")

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
        with st.container(border=True):
            detail_col, amount_col, receipt_col, delete_col = st.columns(
                [0.52, 0.16, 0.22, 0.10],
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
            with delete_col:
                if st.button("Delete", key=f"delete_{expense['id']}", use_container_width=True):
                    delete_expense(expense["id"])
                    st.rerun()

    st.caption(
        f"Expenses, budgets, and attached bills are saved in SQLite at {DB_PATH}."
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
