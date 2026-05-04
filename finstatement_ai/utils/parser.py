"""File ingestion: parse Excel/CSV into a normalized internal schema."""

from __future__ import annotations

import io
import re
from typing import Optional

import pandas as pd

from utils.mappings import keyword_to_line_item, ACCOUNT_NUMBER_PREFIX_MAP


# Standardized internal schema columns:
#   account_number, account_description, py_balance, cy_balance,
#   debit, credit, group, statement, line_item

STD_COLUMNS = [
    "account_number",
    "account_description",
    "py_balance",
    "cy_balance",
    "debit",
    "credit",
    "group",
    "statement",
    "line_item",
]


SOURCE_PRIOR_YEAR_FS = "prior_year_fs"
SOURCE_TRIAL_BALANCE = "trial_balance"


# Possible header label aliases (case/whitespace-insensitive match).
HEADER_ALIASES = {
    "account_number": ["account number", "acct number", "acct no", "account no", "account #", "acct #", "gl account", "gl no"],
    "account_description": ["account description", "account name", "description", "acct description", "account", "gl description"],
    "py_balance": ["py balance", "prior year balance", "prior year", "py amount", "py", "previous year"],
    "cy_balance": ["cy balance", "current year balance", "current year", "cy amount", "cy", "balance", "amount", "ending balance", "net balance"],
    "debit": ["debit", "dr", "debits"],
    "credit": ["credit", "cr", "credits"],
    "group": ["group", "grouping", "category", "classification", "fs group"],
    "statement": ["statement", "fs", "financial statement", "report"],
    "line_item": ["line item", "fs line item", "fs caption", "caption"],
}


def _normalize_header(text: str) -> str:
    return re.sub(r"[^a-z0-9]", " ", str(text).lower()).strip()


def _detect_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map raw dataframe columns to our standardized schema names.

    A given source column is used at most once — first claim wins. Header
    aliases iterate in HEADER_ALIASES order, so account_number is matched
    before account_description (important since e.g. "Account #" normalizes
    to a string that also appears in description aliases).
    """
    mapping: dict[str, str] = {}
    used: set[str] = set()
    normalized = {col: _normalize_header(col) for col in df.columns}
    for std_col, aliases in HEADER_ALIASES.items():
        normalized_aliases = [_normalize_header(a) for a in aliases]
        for raw_col, norm in normalized.items():
            if raw_col in used:
                continue
            if norm in normalized_aliases:
                mapping[std_col] = raw_col
                used.add(raw_col)
                break
    return mapping


def _read_file(uploaded_file, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Read an Excel or CSV upload into a dataframe."""
    name = (uploaded_file.name or "").lower()
    data = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
    if isinstance(uploaded_file, (bytes, bytearray)):
        data = uploaded_file
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(data))
    return pd.read_excel(io.BytesIO(data), sheet_name=sheet_name or 0)


def list_excel_sheets(uploaded_file) -> list[str]:
    """Return sheet names for an Excel upload, or [] for CSV."""
    name = (uploaded_file.name or "").lower()
    if name.endswith(".csv"):
        return []
    data = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
    try:
        xls = pd.ExcelFile(io.BytesIO(data))
        return xls.sheet_names
    except Exception:
        return []
    finally:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)


def _coerce_numeric(series: pd.Series) -> pd.Series:
    """Convert a column to floats, handling parentheses (negatives), commas, $ signs."""
    def parse(val):
        if pd.isna(val):
            return 0.0
        s = str(val).strip()
        if s == "":
            return 0.0
        is_negative = s.startswith("(") and s.endswith(")")
        s = s.replace("(", "").replace(")", "").replace("$", "").replace(",", "").replace(" ", "")
        try:
            num = float(s)
        except ValueError:
            return 0.0
        return -num if is_negative else num
    return series.apply(parse)


def parse_prior_year_fs(uploaded_file, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Parse a prior year financial statement export into the standardized schema."""
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    raw = _read_file(uploaded_file, sheet_name=sheet_name)
    return _normalize_dataframe(raw, source=SOURCE_PRIOR_YEAR_FS)


def parse_trial_balance(uploaded_file, sheet_name: Optional[str] = None) -> pd.DataFrame:
    """Parse a trial balance / grouping report into the standardized schema."""
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    raw = _read_file(uploaded_file, sheet_name=sheet_name)
    return _normalize_dataframe(raw, source=SOURCE_TRIAL_BALANCE)


def _normalize_dataframe(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Convert a raw uploaded dataframe to the standardized schema."""
    if df is None or df.empty:
        return pd.DataFrame(columns=STD_COLUMNS)

    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    column_map = _detect_columns(df)

    out = pd.DataFrame(index=df.index)

    out["account_number"] = df[column_map["account_number"]].astype(str).str.strip() if "account_number" in column_map else ""
    out["account_description"] = df[column_map["account_description"]].astype(str).str.strip() if "account_description" in column_map else ""

    out["py_balance"] = _coerce_numeric(df[column_map["py_balance"]]) if "py_balance" in column_map else 0.0
    out["cy_balance"] = _coerce_numeric(df[column_map["cy_balance"]]) if "cy_balance" in column_map else 0.0

    if "debit" in column_map:
        out["debit"] = _coerce_numeric(df[column_map["debit"]])
    else:
        out["debit"] = 0.0
    if "credit" in column_map:
        out["credit"] = _coerce_numeric(df[column_map["credit"]])
    else:
        out["credit"] = 0.0

    # If we got a trial balance with debit/credit but no cy_balance, derive it.
    if source == SOURCE_TRIAL_BALANCE and out["cy_balance"].abs().sum() == 0:
        out["cy_balance"] = out["debit"] - out["credit"]

    out["group"] = df[column_map["group"]].astype(str).str.strip() if "group" in column_map else ""
    out["statement"] = df[column_map["statement"]].astype(str).str.strip() if "statement" in column_map else ""
    out["line_item"] = df[column_map["line_item"]].astype(str).str.strip() if "line_item" in column_map else ""

    # Drop rows with no description AND no number — likely blank rows / totals.
    mask = (out["account_description"] != "") | (out["account_number"] != "")
    out = out[mask].reset_index(drop=True)

    return out[STD_COLUMNS]


def has_grouping(df: pd.DataFrame) -> bool:
    """True if either the group, statement, or line_item column has any populated values."""
    if df is None or df.empty:
        return False
    for col in ("group", "statement", "line_item"):
        if col in df.columns and df[col].astype(str).str.strip().replace("nan", "").any():
            return True
    return False


def fallback_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Apply heuristic line-item mapping when no grouping column exists."""
    if df is None or df.empty:
        return df
    df = df.copy()
    for idx, row in df.iterrows():
        if not row["line_item"] or row["line_item"] == "nan":
            df.at[idx, "line_item"] = keyword_to_line_item(row["account_description"])
        if not row["group"] or row["group"] == "nan":
            account_no = str(row["account_number"]).strip()
            first_char = account_no[:1] if account_no else ""
            if first_char in ACCOUNT_NUMBER_PREFIX_MAP:
                grp, stmt = ACCOUNT_NUMBER_PREFIX_MAP[first_char]
                df.at[idx, "group"] = grp
                if not row["statement"] or row["statement"] == "nan":
                    df.at[idx, "statement"] = stmt
    return df


def aggregate_by_line_item(df: pd.DataFrame) -> pd.DataFrame:
    """Sum balances by GAAP line_item to get statement-ready figures."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["line_item", "py_balance", "cy_balance"])
    grouped = df.groupby("line_item", as_index=False).agg(
        py_balance=("py_balance", "sum"),
        cy_balance=("cy_balance", "sum"),
    )
    grouped = grouped[grouped["line_item"].astype(str).str.strip() != ""]
    return grouped.reset_index(drop=True)
