"""FinStatement AI - single-file Streamlit app.

Paste-and-run version of the multi-page app. All utilities (parser, AI engine,
checklist rules, PDF builder, account mappings) are inlined. Sidebar radio
replaces the pages/ folder navigation.

Requirements (paste into requirements.txt or install locally):
    streamlit==1.40.1
    anthropic==0.40.0
    openai==1.57.0
    pandas==2.2.3
    openpyxl==3.1.5
    reportlab==4.2.5

Run:
    streamlit run finstatement_ai_single.py
"""

from __future__ import annotations

import io
import json
import re
from datetime import date
from typing import Callable, Optional

import anthropic
import openai
import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether,
)


# =============================================================================
# CONSTANTS / TEMPLATES (from utils/mappings.py)
# =============================================================================

PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
SUPPORTED_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI)

DEFAULT_MODEL_ANTHROPIC = "claude-sonnet-4-5"
DEFAULT_MODEL_OPENAI = "gpt-4o"

PROVIDER_LABELS = {
    PROVIDER_ANTHROPIC: "Anthropic (Claude)",
    PROVIDER_OPENAI: "OpenAI (GPT)",
}
PROVIDER_HELP = {
    PROVIDER_ANTHROPIC: "Get a key at https://console.anthropic.com",
    PROVIDER_OPENAI: "Get a key at https://platform.openai.com/api-keys",
}

STATEMENT_BALANCE_SHEET = "Balance Sheet"
STATEMENT_INCOME = "Income Statement"
STATEMENT_CASH_FLOW = "Cash Flow Statement"
STATEMENT_EQUITY = "Statement of Changes in Equity"
STATEMENT_ACTIVITIES = "Statement of Activities"
STATEMENT_FINANCIAL_POSITION = "Statement of Financial Position"
STATEMENT_FUNCTIONAL_EXPENSES = "Statement of Functional Expenses"

ENTITY_FOR_PROFIT = "For-Profit"
ENTITY_NONPROFIT = "Nonprofit (ASC 958)"

ACCOUNT_NUMBER_PREFIX_MAP = {
    "1": ("Assets", STATEMENT_BALANCE_SHEET),
    "2": ("Liabilities", STATEMENT_BALANCE_SHEET),
    "3": ("Equity", STATEMENT_BALANCE_SHEET),
    "4": ("Revenue", STATEMENT_INCOME),
    "5": ("Cost of Goods Sold", STATEMENT_INCOME),
    "6": ("Operating Expenses", STATEMENT_INCOME),
    "7": ("Operating Expenses", STATEMENT_INCOME),
    "8": ("Other Income/Expense", STATEMENT_INCOME),
    "9": ("Income Tax", STATEMENT_INCOME),
}

BALANCE_SHEET_STRUCTURE_FOR_PROFIT = [
    ("ASSETS", 0, "header"),
    ("Current Assets", 1, "header"),
    ("Cash and cash equivalents", 2, "line"),
    ("Accounts receivable, net", 2, "line"),
    ("Inventory", 2, "line"),
    ("Prepaid expenses", 2, "line"),
    ("Other current assets", 2, "line"),
    ("Total current assets", 1, "subtotal"),
    ("Property, plant and equipment, net", 1, "line"),
    ("Intangible assets, net", 1, "line"),
    ("Goodwill", 1, "line"),
    ("Other assets", 1, "line"),
    ("Total assets", 0, "total"),
    ("LIABILITIES AND STOCKHOLDERS' EQUITY", 0, "header"),
    ("Current Liabilities", 1, "header"),
    ("Accounts payable", 2, "line"),
    ("Accrued expenses", 2, "line"),
    ("Deferred revenue, current", 2, "line"),
    ("Current portion of long-term debt", 2, "line"),
    ("Other current liabilities", 2, "line"),
    ("Total current liabilities", 1, "subtotal"),
    ("Long-term debt, net of current portion", 1, "line"),
    ("Deferred tax liabilities", 1, "line"),
    ("Other long-term liabilities", 1, "line"),
    ("Total liabilities", 0, "subtotal"),
    ("Stockholders' Equity", 1, "header"),
    ("Common stock", 2, "line"),
    ("Additional paid-in capital", 2, "line"),
    ("Retained earnings", 2, "line"),
    ("Accumulated other comprehensive income (loss)", 2, "line"),
    ("Total stockholders' equity", 1, "subtotal"),
    ("Total liabilities and stockholders' equity", 0, "total"),
]

BALANCE_SHEET_STRUCTURE_NONPROFIT = [
    ("ASSETS", 0, "header"),
    ("Cash and cash equivalents", 1, "line"),
    ("Contributions receivable, net", 1, "line"),
    ("Accounts receivable, net", 1, "line"),
    ("Investments", 1, "line"),
    ("Prepaid expenses and other assets", 1, "line"),
    ("Property and equipment, net", 1, "line"),
    ("Total assets", 0, "total"),
    ("LIABILITIES AND NET ASSETS", 0, "header"),
    ("Liabilities", 1, "header"),
    ("Accounts payable and accrued expenses", 2, "line"),
    ("Deferred revenue", 2, "line"),
    ("Notes payable", 2, "line"),
    ("Total liabilities", 1, "subtotal"),
    ("Net Assets", 1, "header"),
    ("Without donor restrictions", 2, "line"),
    ("With donor restrictions", 2, "line"),
    ("Total net assets", 1, "subtotal"),
    ("Total liabilities and net assets", 0, "total"),
]

INCOME_STATEMENT_STRUCTURE = [
    ("Revenue", 0, "line"),
    ("Cost of revenue", 0, "line"),
    ("Gross profit", 0, "subtotal"),
    ("Operating Expenses", 0, "header"),
    ("Selling, general and administrative", 1, "line"),
    ("Research and development", 1, "line"),
    ("Depreciation and amortization", 1, "line"),
    ("Total operating expenses", 0, "subtotal"),
    ("Operating income (loss)", 0, "subtotal"),
    ("Other Income (Expense)", 0, "header"),
    ("Interest income", 1, "line"),
    ("Interest expense", 1, "line"),
    ("Other, net", 1, "line"),
    ("Total other income (expense), net", 0, "subtotal"),
    ("Income (loss) before income taxes", 0, "subtotal"),
    ("Provision for (benefit from) income taxes", 0, "line"),
    ("Net income (loss)", 0, "total"),
]

STATEMENT_OF_ACTIVITIES_STRUCTURE = [
    ("REVENUES, GAINS, AND OTHER SUPPORT", 0, "header"),
    ("Contributions", 1, "line"),
    ("Grants", 1, "line"),
    ("Program service fees", 1, "line"),
    ("Investment income, net", 1, "line"),
    ("Other income", 1, "line"),
    ("Net assets released from restrictions", 1, "line"),
    ("Total revenues, gains, and other support", 0, "subtotal"),
    ("EXPENSES", 0, "header"),
    ("Program services", 1, "line"),
    ("Management and general", 1, "line"),
    ("Fundraising", 1, "line"),
    ("Total expenses", 0, "subtotal"),
    ("Change in net assets", 0, "subtotal"),
    ("Net assets, beginning of year", 0, "line"),
    ("Net assets, end of year", 0, "total"),
]

CASH_FLOW_INDIRECT_STRUCTURE = [
    ("CASH FLOWS FROM OPERATING ACTIVITIES", 0, "header"),
    ("Net income (loss)", 1, "line"),
    ("Adjustments to reconcile net income to net cash:", 1, "header"),
    ("Depreciation and amortization", 2, "line"),
    ("Stock-based compensation", 2, "line"),
    ("Deferred income taxes", 2, "line"),
    ("Changes in operating assets and liabilities:", 1, "header"),
    ("Accounts receivable", 2, "line"),
    ("Inventory", 2, "line"),
    ("Prepaid expenses", 2, "line"),
    ("Accounts payable", 2, "line"),
    ("Accrued expenses", 2, "line"),
    ("Deferred revenue", 2, "line"),
    ("Net cash provided by (used in) operating activities", 0, "subtotal"),
    ("CASH FLOWS FROM INVESTING ACTIVITIES", 0, "header"),
    ("Purchases of property and equipment", 1, "line"),
    ("Purchases of investments", 1, "line"),
    ("Proceeds from sale of investments", 1, "line"),
    ("Net cash provided by (used in) investing activities", 0, "subtotal"),
    ("CASH FLOWS FROM FINANCING ACTIVITIES", 0, "header"),
    ("Proceeds from issuance of debt", 1, "line"),
    ("Repayments of debt", 1, "line"),
    ("Proceeds from issuance of stock", 1, "line"),
    ("Dividends paid", 1, "line"),
    ("Net cash provided by (used in) financing activities", 0, "subtotal"),
    ("Net change in cash and cash equivalents", 0, "subtotal"),
    ("Cash and cash equivalents, beginning of period", 0, "line"),
    ("Cash and cash equivalents, end of period", 0, "total"),
]

CASH_FLOW_DIRECT_STRUCTURE = [
    ("CASH FLOWS FROM OPERATING ACTIVITIES", 0, "header"),
    ("Cash received from customers", 1, "line"),
    ("Cash paid to suppliers and employees", 1, "line"),
    ("Interest paid", 1, "line"),
    ("Income taxes paid", 1, "line"),
    ("Net cash provided by (used in) operating activities", 0, "subtotal"),
    ("CASH FLOWS FROM INVESTING ACTIVITIES", 0, "header"),
    ("Purchases of property and equipment", 1, "line"),
    ("Purchases of investments", 1, "line"),
    ("Proceeds from sale of investments", 1, "line"),
    ("Net cash provided by (used in) investing activities", 0, "subtotal"),
    ("CASH FLOWS FROM FINANCING ACTIVITIES", 0, "header"),
    ("Proceeds from issuance of debt", 1, "line"),
    ("Repayments of debt", 1, "line"),
    ("Proceeds from issuance of stock", 1, "line"),
    ("Dividends paid", 1, "line"),
    ("Net cash provided by (used in) financing activities", 0, "subtotal"),
    ("Net change in cash and cash equivalents", 0, "subtotal"),
    ("Cash and cash equivalents, beginning of period", 0, "line"),
    ("Cash and cash equivalents, end of period", 0, "total"),
]

CHANGES_IN_EQUITY_STRUCTURE = [
    ("Balance, beginning of year", 0, "line"),
    ("Net income (loss)", 0, "line"),
    ("Issuance of common stock", 0, "line"),
    ("Stock-based compensation", 0, "line"),
    ("Dividends declared", 0, "line"),
    ("Other comprehensive income (loss)", 0, "line"),
    ("Balance, end of year", 0, "total"),
]

FUNCTIONAL_EXPENSES_PROGRAMS = ["Program A", "Program B", "Management & General", "Fundraising"]
FUNCTIONAL_EXPENSES_CATEGORIES = [
    "Salaries and wages", "Employee benefits", "Payroll taxes", "Professional fees",
    "Occupancy", "Office expenses", "Information technology", "Travel",
    "Conferences and meetings", "Depreciation", "Other expenses",
]


def get_statement_structure(statement_name, entity_type, cash_flow_method="Indirect"):
    if statement_name in (STATEMENT_BALANCE_SHEET, STATEMENT_FINANCIAL_POSITION):
        if entity_type == ENTITY_NONPROFIT:
            return BALANCE_SHEET_STRUCTURE_NONPROFIT
        return BALANCE_SHEET_STRUCTURE_FOR_PROFIT
    if statement_name == STATEMENT_INCOME:
        return INCOME_STATEMENT_STRUCTURE
    if statement_name == STATEMENT_ACTIVITIES:
        return STATEMENT_OF_ACTIVITIES_STRUCTURE
    if statement_name == STATEMENT_CASH_FLOW:
        return CASH_FLOW_DIRECT_STRUCTURE if cash_flow_method == "Direct" else CASH_FLOW_INDIRECT_STRUCTURE
    if statement_name == STATEMENT_EQUITY:
        return CHANGES_IN_EQUITY_STRUCTURE
    return []


def keyword_to_line_item(description, entity_type=ENTITY_FOR_PROFIT):
    desc = (description or "").lower()
    rules = [
        (["cash", "checking", "savings", "money market"], "Cash and cash equivalents"),
        (["account receivable", "accounts receivable", "a/r", "trade receivable"], "Accounts receivable, net"),
        (["contribution receivable", "pledges receivable"], "Contributions receivable, net"),
        (["inventory", "stock on hand"], "Inventory"),
        (["prepaid"], "Prepaid expenses"),
        (["building", "equipment", "machinery", "furniture", "vehicle", "leasehold improve"], "Property, plant and equipment, net"),
        (["accumulated depreciation"], "Property, plant and equipment, net"),
        (["goodwill"], "Goodwill"),
        (["intangible", "patent", "trademark", "software"], "Intangible assets, net"),
        (["account payable", "accounts payable", "a/p", "trade payable"], "Accounts payable"),
        (["accrued"], "Accrued expenses"),
        (["deferred revenue", "unearned revenue"], "Deferred revenue, current"),
        (["note payable", "loan payable", "line of credit"], "Long-term debt, net of current portion"),
        (["common stock", "capital stock"], "Common stock"),
        (["paid-in capital", "additional paid"], "Additional paid-in capital"),
        (["retained earnings"], "Retained earnings"),
        (["without donor restriction", "unrestricted"], "Without donor restrictions"),
        (["with donor restriction", "temporarily restricted", "permanently restricted"], "With donor restrictions"),
        (["sales", "revenue", "service revenue"], "Revenue"),
        (["contribution income", "donation"], "Contributions"),
        (["grant"], "Grants"),
        (["cost of goods sold", "cost of sales", "cogs"], "Cost of revenue"),
        (["salary", "wages", "payroll"], "Selling, general and administrative"),
        (["rent"], "Selling, general and administrative"),
        (["depreciation expense"], "Depreciation and amortization"),
        (["interest expense"], "Interest expense"),
        (["interest income"], "Interest income"),
        (["income tax", "tax expense", "provision for tax"], "Provision for (benefit from) income taxes"),
    ]
    for keywords, line_item in rules:
        for keyword in keywords:
            if keyword in desc:
                return line_item
    return "Uncategorized"


# =============================================================================
# PARSER (from utils/parser.py)
# =============================================================================

STD_COLUMNS = [
    "account_number", "account_description", "py_balance", "cy_balance",
    "debit", "credit", "group", "statement", "line_item",
]

SOURCE_PRIOR_YEAR_FS = "prior_year_fs"
SOURCE_TRIAL_BALANCE = "trial_balance"

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


def _normalize_header(text):
    return re.sub(r"[^a-z0-9]", " ", str(text).lower()).strip()


def _detect_columns(df):
    mapping = {}
    used = set()
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


def _read_file(uploaded_file, sheet_name=None):
    name = (uploaded_file.name or "").lower()
    data = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
    if isinstance(uploaded_file, (bytes, bytearray)):
        data = uploaded_file
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(data))
    return pd.read_excel(io.BytesIO(data), sheet_name=sheet_name or 0)


def list_excel_sheets(uploaded_file):
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


def _coerce_numeric(series):
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


def _normalize_dataframe(df, source):
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
    out["debit"] = _coerce_numeric(df[column_map["debit"]]) if "debit" in column_map else 0.0
    out["credit"] = _coerce_numeric(df[column_map["credit"]]) if "credit" in column_map else 0.0
    if source == SOURCE_TRIAL_BALANCE and out["cy_balance"].abs().sum() == 0:
        out["cy_balance"] = out["debit"] - out["credit"]
    out["group"] = df[column_map["group"]].astype(str).str.strip() if "group" in column_map else ""
    out["statement"] = df[column_map["statement"]].astype(str).str.strip() if "statement" in column_map else ""
    out["line_item"] = df[column_map["line_item"]].astype(str).str.strip() if "line_item" in column_map else ""
    mask = (out["account_description"] != "") | (out["account_number"] != "")
    out = out[mask].reset_index(drop=True)
    return out[STD_COLUMNS]


def parse_prior_year_fs(uploaded_file, sheet_name=None):
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    raw = _read_file(uploaded_file, sheet_name=sheet_name)
    return _normalize_dataframe(raw, source=SOURCE_PRIOR_YEAR_FS)


def parse_trial_balance(uploaded_file, sheet_name=None):
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    raw = _read_file(uploaded_file, sheet_name=sheet_name)
    return _normalize_dataframe(raw, source=SOURCE_TRIAL_BALANCE)


def has_grouping(df):
    if df is None or df.empty:
        return False
    for col in ("group", "statement", "line_item"):
        if col in df.columns and df[col].astype(str).str.strip().replace("nan", "").any():
            return True
    return False


def fallback_mapping(df):
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


def aggregate_by_line_item(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=["line_item", "py_balance", "cy_balance"])
    grouped = df.groupby("line_item", as_index=False).agg(
        py_balance=("py_balance", "sum"),
        cy_balance=("cy_balance", "sum"),
    )
    grouped = grouped[grouped["line_item"].astype(str).str.strip() != ""]
    return grouped.reset_index(drop=True)


# =============================================================================
# AI ENGINE (dual-provider: Anthropic + OpenAI)
# =============================================================================

SYSTEM_NOTE_DRAFTER = """You are an expert CPA and technical accounting writer drafting GAAP-compliant \
notes to financial statements for {entity_type} entities under U.S. GAAP \
(FASB ASC, including ASC 958 for nonprofits).

Requirements:
- Write in formal, third-person accounting disclosure language.
- Reference the actual dollar amounts you are given. Do not fabricate figures.
- Where a fact is required for the disclosure but is missing from the data, \
insert a placeholder in the form [CONFIRM: <what to confirm>].
- Use proper GAAP terminology.
- Be concise but complete. Do not invent disclosures that are not warranted.
- Note 1 is always Summary of Significant Accounting Policies.
"""


def _call_anthropic(api_key, system, user_prompt, max_tokens, model_override=None):
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_override or DEFAULT_MODEL_ANTHROPIC,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


def _call_openai(api_key, system, user_prompt, max_tokens, want_json=False, model_override=None):
    client = openai.OpenAI(api_key=api_key)
    kwargs = {
        "model": model_override or DEFAULT_MODEL_OPENAI,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
    }
    if want_json:
        kwargs["response_format"] = {"type": "json_object"}
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def _call_llm(provider, api_key, system, user_prompt, max_tokens, want_json=False, model_override=None):
    if provider == PROVIDER_OPENAI:
        return _call_openai(api_key, system, user_prompt, max_tokens, want_json, model_override)
    return _call_anthropic(api_key, system, user_prompt, max_tokens, model_override)


def _first_json_blob(text):
    obj_start = text.find("{")
    arr_start = text.find("[")
    candidates = [i for i in (obj_start, arr_start) if i >= 0]
    if not candidates:
        return None
    start = min(candidates)
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


def _extract_json(text):
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    for chunk in (candidate, _first_json_blob(candidate)):
        if not chunk:
            continue
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    return None


def validate_api_key(provider, api_key):
    if provider not in SUPPORTED_PROVIDERS:
        return False, f"Unsupported provider: {provider}"
    if not api_key or not api_key.strip():
        return False, "API key is empty."
    try:
        if provider == PROVIDER_OPENAI:
            client = openai.OpenAI(api_key=api_key.strip())
            client.chat.completions.create(
                model=DEFAULT_MODEL_OPENAI, max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
        else:
            client = anthropic.Anthropic(api_key=api_key.strip())
            client.messages.create(
                model=DEFAULT_MODEL_ANTHROPIC, max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
        return True, "API key validated."
    except anthropic.AuthenticationError:
        return False, "Invalid Anthropic API key."
    except anthropic.PermissionDeniedError:
        return False, "Anthropic API key lacks permission."
    except anthropic.RateLimitError:
        return False, "Rate limited; the key looks valid. Try again in a moment."
    except anthropic.APIConnectionError:
        return False, "Could not reach the Anthropic API."
    except openai.AuthenticationError:
        return False, "Invalid OpenAI API key."
    except openai.PermissionDeniedError:
        return False, "OpenAI API key lacks permission."
    except openai.RateLimitError:
        return False, "Rate limited; the key looks valid. Try again in a moment."
    except openai.APIConnectionError:
        return False, "Could not reach the OpenAI API."
    except Exception as e:
        return False, f"Unexpected error: {e}"


def suggest_account_mapping(provider, api_key, accounts_df, entity_type):
    if accounts_df is None or accounts_df.empty:
        return accounts_df
    rows = [{
        "account_number": str(row.get("account_number", "")),
        "account_description": str(row.get("account_description", "")),
        "cy_balance": float(row.get("cy_balance", 0) or 0),
    } for _, row in accounts_df.iterrows()]
    user_prompt = f"""You are mapping a chart of accounts to GAAP financial statement \
line items for a {entity_type} entity.

For each account, return:
- statement: one of "Balance Sheet", "Income Statement", "Cash Flow Statement", \
"Statement of Activities", "Statement of Financial Position"
- group: e.g. "Assets", "Liabilities", "Equity", "Revenue", "Operating Expenses"
- line_item: a standard GAAP caption

Return ONLY a JSON object with key "accounts" mapping to an array. Each array \
element MUST have keys: account_number, account_description, statement, group, line_item.

Accounts to classify:
{json.dumps(rows, indent=2)}
"""
    text = _call_llm(
        provider=provider, api_key=api_key,
        system="You are an expert CPA classifying chart-of-accounts entries to GAAP financial statement line items. Return strict JSON only.",
        user_prompt=user_prompt, max_tokens=8000, want_json=True,
    )
    parsed = _extract_json(text)
    if isinstance(parsed, dict) and "accounts" in parsed:
        parsed = parsed["accounts"]
    if not isinstance(parsed, list):
        return accounts_df
    by_key = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        key = (str(item.get("account_number", "")).strip(), str(item.get("account_description", "")).strip())
        by_key[key] = item
    out = accounts_df.copy()
    for idx, row in out.iterrows():
        key = (str(row.get("account_number", "")).strip(), str(row.get("account_description", "")).strip())
        match = by_key.get(key)
        if not match:
            continue
        if match.get("statement"): out.at[idx, "statement"] = match["statement"]
        if match.get("group"): out.at[idx, "group"] = match["group"]
        if match.get("line_item"): out.at[idx, "line_item"] = match["line_item"]
    return out


def generate_all_notes(provider, api_key, entity_name, entity_type, fiscal_year_end,
                       statements_summary, required_notes, prior_year_notes_text=""):
    pyn = ""
    if prior_year_notes_text:
        pyn = f"\nPrior year note language (use as a starting point; update figures):\n{prior_year_notes_text[:6000]}\n"
    user_prompt = f"""Draft the full set of notes to financial statements for the following entity.

Entity: {entity_name}
Entity type: {entity_type}
Fiscal year end: {fiscal_year_end}

Financial statement summary:
{json.dumps(statements_summary, indent=2, default=str)}

Required notes (in order):
{json.dumps(required_notes, indent=2)}
{pyn}
Return ONLY a JSON object with key "notes" mapping to an array. Each array \
element MUST have keys:
- title (e.g., "Note 1 - Summary of Significant Accounting Policies")
- narrative (formal disclosure prose; use real dollar figures; use [CONFIRM: ...] placeholders)
- table_data (array of row objects; [] if no table)
- table_columns (array of column names matching table_data keys; [] if no table)

For notes with a schedule (debt, lease maturity, PP&E, net asset rollforward, etc.), \
populate table_data and table_columns. Note 1 is always Summary of Significant Accounting Policies.
"""
    text = _call_llm(
        provider=provider, api_key=api_key,
        system=SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type),
        user_prompt=user_prompt,
        max_tokens=16000 if provider == PROVIDER_ANTHROPIC else 8000,
        want_json=True,
    )
    parsed = _extract_json(text)
    if isinstance(parsed, dict) and "notes" in parsed:
        parsed = parsed["notes"]
    if not isinstance(parsed, list):
        return []
    cleaned = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        cleaned.append({
            "title": str(item.get("title", "Untitled Note")),
            "narrative": str(item.get("narrative", "")),
            "table_data": item.get("table_data") if isinstance(item.get("table_data"), list) else [],
            "table_columns": item.get("table_columns") if isinstance(item.get("table_columns"), list) else [],
        })
    return cleaned


def regenerate_note(provider, api_key, entity_name, entity_type, note_title,
                    statements_summary, instruction="", mode="redo", existing_narrative=""):
    if mode == "redo":
        directive = "Generate this note from scratch, taking a different approach than before."
    elif mode == "expand":
        directive = "Expand the existing note: add detail, sub-sections, address all relevant GAAP requirements."
    else:
        directive = instruction or "Improve this note."
    user_prompt = f"""Entity: {entity_name}
Entity type: {entity_type}
Note: {note_title}

Financial statement summary:
{json.dumps(statements_summary, indent=2, default=str)}

Existing narrative (may be empty):
{existing_narrative}

Instruction:
{directive}

Return ONLY a JSON object with keys: title, narrative, table_data, table_columns.
"""
    text = _call_llm(
        provider=provider, api_key=api_key,
        system=SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type),
        user_prompt=user_prompt, max_tokens=6000, want_json=True,
    )
    parsed = _extract_json(text)
    if not isinstance(parsed, dict):
        return {"title": note_title, "narrative": text.strip(), "table_data": [], "table_columns": []}
    return {
        "title": str(parsed.get("title", note_title)),
        "narrative": str(parsed.get("narrative", "")),
        "table_data": parsed.get("table_data") if isinstance(parsed.get("table_data"), list) else [],
        "table_columns": parsed.get("table_columns") if isinstance(parsed.get("table_columns"), list) else [],
    }


def generate_single_note(provider, api_key, entity_name, entity_type, note_topic, statements_summary):
    user_prompt = f"""Draft a single GAAP-compliant note for the topic below.

Entity: {entity_name}
Entity type: {entity_type}
Note topic: {note_topic}

Financial statement summary:
{json.dumps(statements_summary, indent=2, default=str)}

Return ONLY a JSON object with keys: title, narrative, table_data, table_columns.
"""
    text = _call_llm(
        provider=provider, api_key=api_key,
        system=SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type),
        user_prompt=user_prompt, max_tokens=4000, want_json=True,
    )
    parsed = _extract_json(text)
    if not isinstance(parsed, dict):
        return {"title": note_topic, "narrative": text.strip(), "table_data": [], "table_columns": []}
    return {
        "title": str(parsed.get("title", note_topic)),
        "narrative": str(parsed.get("narrative", "")),
        "table_data": parsed.get("table_data") if isinstance(parsed.get("table_data"), list) else [],
        "table_columns": parsed.get("table_columns") if isinstance(parsed.get("table_columns"), list) else [],
    }


# =============================================================================
# CHECKLIST RULES (from utils/checklist.py)
# =============================================================================

REQUIRED, RECOMMENDED, NA = "Required", "Recommended", "N/A"

CATEGORIES = [
    "Accounting Policies", "Cash and Receivables", "Inventory", "Property and Equipment",
    "Intangibles and Goodwill", "Investments and Fair Value", "Debt", "Leases",
    "Income Taxes", "Revenue", "Net Assets", "Functional Expenses",
    "Compensation and Benefits", "Commitments and Contingencies", "Related Party",
    "Subsequent Events", "Risks and Uncertainties",
]


def _has_balance(facts, line_keywords, threshold=0.0):
    summary = facts.get("statements_summary", {}) or {}
    for stmt_lines in summary.values():
        if not isinstance(stmt_lines, list):
            continue
        for row in stmt_lines:
            line = str(row.get("line_item", "")).lower()
            cy = abs(float(row.get("cy_balance", 0) or 0))
            py = abs(float(row.get("py_balance", 0) or 0))
            if any(kw in line for kw in line_keywords) and (cy > threshold or py > threshold):
                return True
    return False


def _is_nonprofit(facts):
    return facts.get("entity_type") == ENTITY_NONPROFIT


def _is_for_profit(facts):
    return facts.get("entity_type") == ENTITY_FOR_PROFIT


def _statements_include(facts, name):
    selected = facts.get("statements_selected", []) or []
    return any(name.lower() in str(s).lower() for s in selected)


RULES = [
    ("note_01_sigacct", "Summary of Significant Accounting Policies", "Accounting Policies", REQUIRED, lambda f: True),
    ("note_org_nature", "Nature of Operations / Organization", "Accounting Policies", REQUIRED, lambda f: True),
    ("note_basis", "Basis of Presentation", "Accounting Policies", REQUIRED, lambda f: True),
    ("note_estimates", "Use of Estimates", "Accounting Policies", REQUIRED, lambda f: True),
    ("note_concentrations", "Concentrations of Credit Risk", "Risks and Uncertainties", RECOMMENDED, lambda f: True),
    ("note_cash", "Cash and Cash Equivalents", "Cash and Receivables", REQUIRED, lambda f: _has_balance(f, ["cash"])),
    ("note_ar", "Accounts Receivable and Allowance for Credit Losses (CECL, ASC 326)", "Cash and Receivables", REQUIRED, lambda f: _has_balance(f, ["receivable"])),
    ("note_inventory", "Inventory", "Inventory", REQUIRED, lambda f: _has_balance(f, ["inventory"])),
    ("note_ppe", "Property, Plant and Equipment", "Property and Equipment", REQUIRED, lambda f: _has_balance(f, ["property", "equipment", "plant"])),
    ("note_intangibles", "Intangible Assets", "Intangibles and Goodwill", REQUIRED, lambda f: _has_balance(f, ["intangible", "patent", "trademark"])),
    ("note_goodwill", "Goodwill (ASC 350)", "Intangibles and Goodwill", REQUIRED, lambda f: _has_balance(f, ["goodwill"])),
    ("note_investments", "Investments and Fair Value Measurements (ASC 820)", "Investments and Fair Value", REQUIRED, lambda f: _has_balance(f, ["investment"])),
    ("note_debt", "Long-Term Debt", "Debt", REQUIRED, lambda f: _has_balance(f, ["debt", "note payable", "loan", "bond"])),
    ("note_leases", "Leases (ASC 842)", "Leases", REQUIRED, lambda f: bool(f.get("has_leases"))),
    ("note_income_taxes", "Income Taxes (ASC 740)", "Income Taxes", REQUIRED, lambda f: _is_for_profit(f) and (_has_balance(f, ["income tax", "tax"]) or bool(f.get("has_income_taxes")))),
    ("note_revenue", "Revenue Recognition (ASC 606)", "Revenue", REQUIRED, lambda f: _is_for_profit(f) and _has_balance(f, ["revenue", "sales"])),
    ("note_net_assets", "Net Assets (ASC 958)", "Net Assets", REQUIRED, lambda f: _is_nonprofit(f)),
    ("note_donor_restrictions", "Donor Restrictions and Releases", "Net Assets", REQUIRED, lambda f: _is_nonprofit(f) and _has_balance(f, ["restriction"])),
    ("note_liquidity", "Liquidity and Availability of Resources (ASC 958-210-50)", "Net Assets", REQUIRED, lambda f: _is_nonprofit(f)),
    ("note_functional_expenses", "Functional Expenses Allocation", "Functional Expenses", REQUIRED, lambda f: _is_nonprofit(f) or _statements_include(f, "Functional Expenses")),
    ("note_contributions", "Contributions and Revenue Recognition", "Revenue", REQUIRED, lambda f: _is_nonprofit(f)),
    ("note_endowment", "Endowment Funds and UPMIFA Disclosures", "Net Assets", RECOMMENDED, lambda f: _is_nonprofit(f) and _has_balance(f, ["endowment"])),
    ("note_employee_benefits", "Employee Benefit Plans", "Compensation and Benefits", RECOMMENDED, lambda f: bool(f.get("has_benefit_plans"))),
    ("note_stock_based_comp", "Stock-Based Compensation (ASC 718)", "Compensation and Benefits", REQUIRED, lambda f: _is_for_profit(f) and bool(f.get("has_stock_comp"))),
    ("note_equity", "Stockholders' Equity", "Net Assets", REQUIRED, lambda f: _is_for_profit(f)),
    ("note_commitments", "Commitments and Contingencies", "Commitments and Contingencies", REQUIRED, lambda f: True),
    ("note_related_party", "Related Party Transactions", "Related Party", RECOMMENDED, lambda f: True),
    ("note_subsequent", "Subsequent Events", "Subsequent Events", REQUIRED, lambda f: True),
    ("note_risks", "Risks and Uncertainties (ASC 275)", "Risks and Uncertainties", REQUIRED, lambda f: True),
    ("note_recent_pronouncements", "Recent Accounting Pronouncements", "Accounting Policies", RECOMMENDED, lambda f: True),
]


def build_checklist(facts):
    items = []
    for rule_id, title, category, default_status, predicate in RULES:
        try:
            triggered = bool(predicate(facts))
        except Exception:
            triggered = False
        status = default_status if triggered else NA
        items.append({
            "id": rule_id, "title": title, "category": category,
            "status": status, "complete": False,
            "default_status": default_status, "auto_triggered": triggered,
        })
    return items


def merge_checklist(existing, rebuilt):
    by_id = {item["id"]: item for item in (existing or [])}
    merged = []
    for item in rebuilt:
        prior = by_id.get(item["id"])
        if prior:
            item = dict(item)
            item["status"] = prior.get("status", item["status"])
            item["complete"] = prior.get("complete", item["complete"])
        merged.append(item)
    return merged


def progress_counts(checklist):
    required = [c for c in (checklist or []) if c.get("status") == REQUIRED]
    completed = [c for c in required if c.get("complete")]
    return len(completed), len(required)


def required_note_titles(checklist):
    return [c["title"] for c in (checklist or []) if c.get("status") in (REQUIRED, RECOMMENDED)]


STANDARD_NOTE_CATALOG = [
    "Summary of Significant Accounting Policies", "Nature of Operations / Organization",
    "Cash and Cash Equivalents", "Accounts Receivable",
    "Allowance for Credit Losses (CECL, ASC 326)", "Inventory",
    "Property, Plant and Equipment", "Intangible Assets", "Goodwill (ASC 350)",
    "Investments and Fair Value Measurements (ASC 820)", "Long-Term Debt",
    "Leases (ASC 842)", "Income Taxes (ASC 740)", "Revenue Recognition (ASC 606)",
    "Stock-Based Compensation (ASC 718)", "Stockholders' Equity",
    "Net Assets (ASC 958)", "Donor Restrictions and Releases",
    "Liquidity and Availability of Resources",
    "Endowment Funds and UPMIFA Disclosures", "Functional Expenses Allocation",
    "Contributions and Revenue Recognition", "Employee Benefit Plans",
    "Commitments and Contingencies", "Related Party Transactions",
    "Subsequent Events", "Risks and Uncertainties (ASC 275)",
    "Concentrations of Credit Risk", "Recent Accounting Pronouncements",
]


# =============================================================================
# PDF BUILDER (from utils/pdf_builder.py)
# =============================================================================

def _pdf_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], fontName="Helvetica-Bold",
                                 fontSize=22, leading=28, alignment=TA_CENTER, spaceAfter=12),
        "subtitle": ParagraphStyle("Subtitle", parent=base["Normal"], fontName="Helvetica",
                                    fontSize=14, leading=20, alignment=TA_CENTER, spaceAfter=8),
        "h1": ParagraphStyle("H1", parent=base["Heading1"], fontName="Helvetica-Bold",
                              fontSize=16, leading=20, spaceBefore=12, spaceAfter=8),
        "h2": ParagraphStyle("H2", parent=base["Heading2"], fontName="Helvetica-Bold",
                              fontSize=12, leading=16, spaceBefore=10, spaceAfter=6),
        "body": ParagraphStyle("Body", parent=base["Normal"], fontName="Helvetica",
                                fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=6),
        "small": ParagraphStyle("Small", parent=base["Normal"], fontName="Helvetica",
                                 fontSize=9, leading=12, alignment=TA_CENTER),
    }


def _fmt_currency(val):
    try:
        num = float(val)
    except (TypeError, ValueError):
        return str(val) if val not in (None, "") else ""
    if num == 0:
        return "$ -"
    sign = "-" if num < 0 else ""
    return f"{sign}${abs(num):,.0f}"


def _header_footer(canvas, doc, entity_name):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    width, _ = LETTER
    canvas.drawString(0.75 * inch, 0.5 * inch, entity_name)
    canvas.drawRightString(width - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _build_statement_table(rows, current_label, prior_label):
    table_data = [["", current_label, prior_label]]
    style_cmds = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
    ]
    for i, row in enumerate(rows, start=1):
        level = int(row.get("level", 0) or 0)
        kind = row.get("kind", "line")
        indent = "    " * level
        label = f"{indent}{row.get('line_item', '')}"
        cy = _fmt_currency(row.get("cy_balance"))
        py = _fmt_currency(row.get("py_balance"))
        if kind == "header":
            table_data.append([label, "", ""])
            style_cmds.append(("FONT", (0, i), (0, i), "Helvetica-Bold", 10))
        elif kind == "subtotal":
            table_data.append([label, cy, py])
            style_cmds.append(("FONT", (0, i), (-1, i), "Helvetica-Bold", 10))
            style_cmds.append(("LINEABOVE", (1, i), (-1, i), 0.5, colors.black))
        elif kind == "total":
            table_data.append([label, cy, py])
            style_cmds.append(("FONT", (0, i), (-1, i), "Helvetica-Bold", 10))
            style_cmds.append(("LINEABOVE", (1, i), (-1, i), 0.5, colors.black))
            style_cmds.append(("LINEBELOW", (1, i), (-1, i), 1.25, colors.black))
        else:
            table_data.append([label, cy, py])
    table = Table(table_data, colWidths=[3.6 * inch, 1.4 * inch, 1.4 * inch], repeatRows=1)
    table.setStyle(TableStyle(style_cmds))
    return table


def _build_data_table(rows, columns):
    if not rows or not columns:
        return None
    table_data = [list(columns)]
    for row in rows:
        out_row = []
        for col in columns:
            val = row.get(col, "")
            if isinstance(val, (int, float)):
                out_row.append(_fmt_currency(val))
            else:
                out_row.append(str(val) if val is not None else "")
        table_data.append(out_row)
    col_widths = [(6.4 * inch) / len(columns)] * len(columns)
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_pdf(entity_name, entity_type, fiscal_year_end, statements, notes,
              checklist=None, include_checklist_appendix=False):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=LETTER,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch, bottomMargin=0.75 * inch,
        title=f"{entity_name} - Financial Statements", author="FinStatement AI",
    )
    styles = _pdf_styles()
    story = []
    story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph(entity_name or "Entity Name", styles["title"]))
    story.append(Paragraph("Financial Statements", styles["subtitle"]))
    fye_str = fiscal_year_end if isinstance(fiscal_year_end, str) else str(fiscal_year_end)
    story.append(Paragraph(f"For the year ended {fye_str}", styles["subtitle"]))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(f"({entity_type})", styles["small"]))
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph("See accompanying notes to financial statements.", styles["small"]))
    story.append(PageBreak())

    cy_label = f"As of/For year ended {fye_str}"
    py_label = "Prior Year"
    for stmt_name, rows in (statements or {}).items():
        story.append(Paragraph(entity_name or "", styles["h2"]))
        story.append(Paragraph(stmt_name, styles["h1"]))
        story.append(Paragraph(cy_label, styles["small"]))
        story.append(Spacer(1, 0.15 * inch))
        if rows:
            story.append(_build_statement_table(rows, cy_label, py_label))
        else:
            story.append(Paragraph("(No data available for this statement.)", styles["body"]))
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("See accompanying notes to financial statements.", styles["small"]))
        story.append(PageBreak())

    if notes:
        story.append(Paragraph("Notes to Financial Statements", styles["h1"]))
        story.append(Spacer(1, 0.1 * inch))
        for note in notes:
            block = [Paragraph(note.get("title", "Note"), styles["h2"])]
            narrative = note.get("narrative", "")
            if narrative:
                safe = narrative.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                for para in safe.split("\n\n"):
                    if para.strip():
                        block.append(Paragraph(para.replace("\n", "<br/>"), styles["body"]))
            table_data = note.get("table_data") or []
            table_columns = note.get("table_columns") or []
            if table_data and table_columns:
                tbl = _build_data_table(table_data, table_columns)
                if tbl is not None:
                    block.append(Spacer(1, 0.05 * inch))
                    block.append(tbl)
            block.append(Spacer(1, 0.2 * inch))
            story.append(KeepTogether(block))

    if include_checklist_appendix and checklist:
        story.append(PageBreak())
        story.append(Paragraph("GAAP Disclosure Checklist", styles["h1"]))
        story.append(Spacer(1, 0.1 * inch))
        rows = [["Disclosure", "Category", "Status", "Complete"]]
        for item in checklist:
            rows.append([
                item.get("title", ""), item.get("category", ""),
                item.get("status", ""), "Yes" if item.get("complete") else "No",
            ])
        tbl = Table(rows, colWidths=[3.0 * inch, 1.5 * inch, 1.0 * inch, 0.9 * inch], repeatRows=1)
        tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl)

    on_page = lambda c, d: _header_footer(c, d, entity_name or "")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buffer.seek(0)
    return buffer.read()


def build_session_excel(parsed_tb, statements, notes):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if parsed_tb is not None and not parsed_tb.empty:
            parsed_tb.to_excel(writer, sheet_name="TB_Mapped", index=False)
        else:
            pd.DataFrame(columns=["account_number", "account_description"]).to_excel(writer, sheet_name="TB_Mapped", index=False)

        statements_rows = []
        for stmt_name, rows in (statements or {}).items():
            for row in rows or []:
                statements_rows.append({
                    "Statement": stmt_name, "line_item": row.get("line_item", ""),
                    "level": row.get("level", 0), "kind": row.get("kind", "line"),
                    "cy_balance": row.get("cy_balance", 0), "py_balance": row.get("py_balance", 0),
                })
        if statements_rows:
            pd.DataFrame(statements_rows).to_excel(writer, sheet_name="Statements", index=False)
        else:
            pd.DataFrame(columns=["Statement", "line_item", "cy_balance", "py_balance"]).to_excel(writer, sheet_name="Statements", index=False)

        note_text_rows = [{"title": n.get("title", ""), "narrative": n.get("narrative", "")} for n in (notes or [])]
        if note_text_rows:
            pd.DataFrame(note_text_rows).to_excel(writer, sheet_name="Notes_Text", index=False)
        else:
            pd.DataFrame(columns=["title", "narrative"]).to_excel(writer, sheet_name="Notes_Text", index=False)

        note_table_rows = []
        for n in (notes or []):
            title = n.get("title", "")
            for row in (n.get("table_data") or []):
                if isinstance(row, dict):
                    out = {"note_title": title}
                    out.update(row)
                    note_table_rows.append(out)
        if note_table_rows:
            pd.DataFrame(note_table_rows).to_excel(writer, sheet_name="Notes_Tables", index=False)
        else:
            pd.DataFrame(columns=["note_title"]).to_excel(writer, sheet_name="Notes_Tables", index=False)

    buffer.seek(0)
    return buffer.read()


# =============================================================================
# SESSION STATE
# =============================================================================

st.set_page_config(page_title="FinStatement AI", page_icon="📊", layout="wide", initial_sidebar_state="expanded")


def init_session_state():
    defaults = {
        "provider": PROVIDER_ANTHROPIC,
        "api_key": "", "api_key_validated": False,
        "entity_type": ENTITY_FOR_PROFIT, "basis": "Accrual",
        "entity_name": "", "fiscal_year_end": None,
        "statements_selected": [], "cash_flow_method": "Indirect",
        "uploaded_source_type": "", "raw_uploaded_filename": "",
        "parsed_tb": None, "py_notes_text": "",
        "statements": {}, "checklist": [], "notes": [],
        "facts": {"has_leases": False, "has_income_taxes": False,
                  "has_stock_comp": False, "has_benefit_plans": False},
        "current_page": "Home",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_session():
    keys = list(st.session_state.keys())
    for k in keys:
        del st.session_state[k]
    init_session_state()


# =============================================================================
# SHARED UI
# =============================================================================

def build_statements_summary():
    summary = {}
    for stmt_name, rows in (st.session_state.statements or {}).items():
        out = []
        for row in rows or []:
            if row.get("kind") == "header":
                continue
            out.append({
                "line_item": row.get("line_item", ""),
                "cy_balance": row.get("cy_balance", 0),
                "py_balance": row.get("py_balance", 0),
            })
        summary[stmt_name] = out
    return summary


def render_checklist_sidebar(key_suffix=""):
    facts = {
        "entity_type": st.session_state.entity_type,
        "statements_selected": st.session_state.statements_selected,
        "statements_summary": build_statements_summary(),
        **st.session_state.facts,
    }
    rebuilt = build_checklist(facts)
    st.session_state.checklist = merge_checklist(st.session_state.checklist, rebuilt)

    st.sidebar.subheader("GAAP Disclosure Checklist")
    completed, total = progress_counts(st.session_state.checklist)
    if total:
        st.sidebar.progress(completed / total, text=f"{completed} of {total} required disclosures complete")
    else:
        st.sidebar.caption("No required disclosures triggered yet.")

    by_category = {}
    for item in st.session_state.checklist:
        by_category.setdefault(item["category"], []).append(item)

    for category in CATEGORIES:
        items = by_category.get(category, [])
        if not items:
            continue
        with st.sidebar.expander(category, expanded=False):
            for item in items:
                cols = st.columns([1, 5])
                with cols[0]:
                    item["complete"] = st.checkbox(
                        " ", value=item.get("complete", False),
                        key=f"chk_{key_suffix}_{item['id']}", label_visibility="collapsed",
                    )
                with cols[1]:
                    badge = {REQUIRED: "🔴", RECOMMENDED: "🟡", NA: "⚪"}[item.get("status", NA)]
                    st.markdown(f"{badge} **{item['title']}**")
                    item["status"] = st.selectbox(
                        "Status", [REQUIRED, RECOMMENDED, NA],
                        index=[REQUIRED, RECOMMENDED, NA].index(item.get("status", NA)),
                        key=f"sts_{key_suffix}_{item['id']}", label_visibility="collapsed",
                    )


# =============================================================================
# PAGE: UPLOAD
# =============================================================================

def page_upload():
    st.title("Upload")
    st.subheader("Entity setup")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.entity_type = st.selectbox(
            "Entity Type", [ENTITY_FOR_PROFIT, ENTITY_NONPROFIT],
            index=[ENTITY_FOR_PROFIT, ENTITY_NONPROFIT].index(st.session_state.entity_type),
        )
        st.session_state.basis = st.selectbox(
            "Basis of Presentation", ["Accrual", "Cash"],
            index=["Accrual", "Cash"].index(st.session_state.basis),
        )
        st.session_state.entity_name = st.text_input(
            "Entity Name", value=st.session_state.entity_name, placeholder="e.g., Acme, Inc.",
        )
    with col2:
        default_fye = st.session_state.fiscal_year_end or date(date.today().year - 1, 12, 31)
        st.session_state.fiscal_year_end = st.date_input("Fiscal Year End", value=default_fye)

    is_nonprofit = st.session_state.entity_type == ENTITY_NONPROFIT
    if is_nonprofit:
        all_options = [STATEMENT_FINANCIAL_POSITION, STATEMENT_ACTIVITIES, STATEMENT_CASH_FLOW, STATEMENT_FUNCTIONAL_EXPENSES]
        default = list(all_options)
    else:
        all_options = [STATEMENT_BALANCE_SHEET, STATEMENT_INCOME, STATEMENT_CASH_FLOW, STATEMENT_EQUITY]
        default = [STATEMENT_BALANCE_SHEET, STATEMENT_INCOME, STATEMENT_CASH_FLOW]

    selected = st.session_state.statements_selected or default
    selected = [s for s in selected if s in all_options]
    st.session_state.statements_selected = st.multiselect(
        "Statements to Prepare", options=all_options, default=selected,
    )

    if STATEMENT_CASH_FLOW in st.session_state.statements_selected:
        st.session_state.cash_flow_method = st.radio(
            "Cash Flow Method", ["Indirect", "Direct"],
            index=["Indirect", "Direct"].index(st.session_state.cash_flow_method), horizontal=True,
        )

    st.divider()
    st.markdown("**Engagement-specific flags** (drive the GAAP disclosure checklist):")
    fcols = st.columns(4)
    with fcols[0]:
        st.session_state.facts["has_leases"] = st.checkbox("Has leases (ASC 842)", value=st.session_state.facts.get("has_leases", False))
    with fcols[1]:
        st.session_state.facts["has_income_taxes"] = st.checkbox("Has income tax provision", value=st.session_state.facts.get("has_income_taxes", False))
    with fcols[2]:
        st.session_state.facts["has_stock_comp"] = st.checkbox("Has stock-based compensation", value=st.session_state.facts.get("has_stock_comp", False))
    with fcols[3]:
        st.session_state.facts["has_benefit_plans"] = st.checkbox("Has employee benefit plans", value=st.session_state.facts.get("has_benefit_plans", False))

    st.divider()
    st.subheader("Upload source data")
    source_type = st.radio(
        "Source type",
        ["Trial Balance / Grouping Report", "Prior Year Financial Statement"],
        index=0 if st.session_state.uploaded_source_type != "prior_year_fs" else 1,
    )

    uploaded = st.file_uploader("Upload Excel or CSV", type=["xlsx", "xls", "csv"], accept_multiple_files=False)
    if uploaded is not None:
        sheet_name = None
        sheets = list_excel_sheets(uploaded)
        if sheets:
            sheet_name = st.selectbox("Sheet", sheets)

        if st.button("Parse upload", type="primary"):
            with st.spinner("Parsing uploaded file..."):
                try:
                    if source_type == "Prior Year Financial Statement":
                        df = parse_prior_year_fs(uploaded, sheet_name=sheet_name)
                        st.session_state.uploaded_source_type = "prior_year_fs"
                    else:
                        df = parse_trial_balance(uploaded, sheet_name=sheet_name)
                        st.session_state.uploaded_source_type = "trial_balance"
                except Exception as e:
                    st.error(f"Could not parse the upload: {e}")
                    return

            if df is None or df.empty:
                st.error("The upload was parsed but no rows were detected.")
                return

            st.session_state.raw_uploaded_filename = uploaded.name

            if not has_grouping(df) and st.session_state.uploaded_source_type == "trial_balance":
                st.info("No grouping column detected — asking the LLM to suggest mappings.")
                try:
                    with st.spinner("Generating account mappings..."):
                        df = suggest_account_mapping(
                            provider=st.session_state.provider,
                            api_key=st.session_state.api_key,
                            accounts_df=df, entity_type=st.session_state.entity_type,
                        )
                except Exception as e:
                    st.error(f"AI mapping failed; falling back to keyword heuristics. ({e})")
                df = fallback_mapping(df)

            st.session_state.parsed_tb = df
            st.success(f"Parsed {len(df)} rows from {uploaded.name}.")

    if st.session_state.parsed_tb is not None and not st.session_state.parsed_tb.empty:
        st.subheader("Data preview & corrections")
        st.caption("Edit any row to fix mapping errors before proceeding to Statements.")
        edited = st.data_editor(
            st.session_state.parsed_tb, num_rows="dynamic", use_container_width=True, key="tb_editor",
            column_config={
                "py_balance": st.column_config.NumberColumn("Prior Year", format="$%.2f"),
                "cy_balance": st.column_config.NumberColumn("Current Year", format="$%.2f"),
                "debit": st.column_config.NumberColumn("Debit", format="$%.2f"),
                "credit": st.column_config.NumberColumn("Credit", format="$%.2f"),
            },
        )
        if st.button("Save edits"):
            st.session_state.parsed_tb = edited
            st.success("Edits saved.")
        st.info("Continue to **Statements** in the sidebar.")


# =============================================================================
# PAGE: STATEMENTS
# =============================================================================

def seed_statement_from_template(stmt_name):
    template = get_statement_structure(stmt_name, st.session_state.entity_type, st.session_state.cash_flow_method)
    aggregated = pd.DataFrame()
    if st.session_state.parsed_tb is not None and not st.session_state.parsed_tb.empty:
        aggregated = aggregate_by_line_item(st.session_state.parsed_tb)
    lookup = {}
    if not aggregated.empty:
        for _, r in aggregated.iterrows():
            lookup[str(r["line_item"]).strip().lower()] = (float(r["cy_balance"]), float(r["py_balance"]))
    rows = []
    for line_item, level, kind in template:
        cy, py = (0.0, 0.0)
        if kind == "line":
            cy, py = lookup.get(line_item.lower(), (0.0, 0.0))
        rows.append({"line_item": line_item, "level": level, "kind": kind, "cy_balance": cy, "py_balance": py})
    return rows


def seed_functional_expenses():
    rows = []
    for cat in FUNCTIONAL_EXPENSES_CATEGORIES:
        row = {"line_item": cat, "level": 0, "kind": "line"}
        for p in FUNCTIONAL_EXPENSES_PROGRAMS:
            row[p] = 0.0
        row["Total"] = 0.0
        rows.append(row)
    rows.append({"line_item": "Total expenses", "level": 0, "kind": "total",
                 **{p: 0.0 for p in FUNCTIONAL_EXPENSES_PROGRAMS}, "Total": 0.0})
    return rows


def ensure_statements_seeded():
    selected = st.session_state.statements_selected or []
    statements = st.session_state.statements or {}
    for stmt in selected:
        if stmt not in statements or not statements[stmt]:
            if stmt == STATEMENT_FUNCTIONAL_EXPENSES:
                statements[stmt] = seed_functional_expenses()
            else:
                statements[stmt] = seed_statement_from_template(stmt)
    for stmt in list(statements.keys()):
        if stmt not in selected:
            statements.pop(stmt, None)
    st.session_state.statements = statements


def recalculate_subtotals(rows):
    """Level-aware subtotal/total recalculation. See docstring in original
    multi-file version for the algorithm description."""
    out = [dict(r) for r in rows]
    n = len(out)
    for i in range(n):
        row = out[i]
        kind = row.get("kind", "line")
        if kind not in ("subtotal", "total"):
            continue
        my_level = int(row.get("level", 0) or 0)
        is_total = kind == "total"
        scope_start = 0
        for j in range(i - 1, -1, -1):
            jrow = out[j]
            jkind = jrow.get("kind", "line")
            jlevel = int(jrow.get("level", 0) or 0)
            if is_total:
                if jkind == "total" and jlevel <= my_level:
                    scope_start = j + 1
                    break
            else:
                if jkind in ("subtotal", "total") and jlevel <= my_level:
                    scope_start = j + 1
                    break
        cy = py = 0.0
        sib_running_cy = sib_running_py = 0.0
        sib_pending_cy = sib_pending_py = 0.0
        for j in range(scope_start, i):
            jrow = out[j]
            jkind = jrow.get("kind", "line")
            jlevel = int(jrow.get("level", 0) or 0)
            if jkind == "header":
                continue
            try:
                jcy = float(jrow.get("cy_balance", 0) or 0)
                jpy = float(jrow.get("py_balance", 0) or 0)
            except (TypeError, ValueError):
                continue
            if jkind == "line":
                sib_pending_cy += jcy
                sib_pending_py += jpy
            elif jkind == "subtotal" and jlevel > my_level:
                sib_running_cy += jcy
                sib_running_py += jpy
                sib_pending_cy = sib_pending_py = 0.0
            elif jkind == "subtotal" and jlevel == my_level:
                cy += jcy
                py += jpy
                sib_running_cy = sib_running_py = 0.0
                sib_pending_cy = sib_pending_py = 0.0
        cy += sib_running_cy + sib_pending_cy
        py += sib_running_py + sib_pending_py
        row["cy_balance"] = cy
        row["py_balance"] = py
    return out


def balance_check_balance_sheet(rows):
    cy_assets = 0.0
    cy_liab_equity = 0.0
    seen_assets_total = False
    for row in rows:
        line = (row.get("line_item") or "").lower()
        cy = float(row.get("cy_balance", 0) or 0)
        if "total assets" == line:
            cy_assets = cy
            seen_assets_total = True
        elif "total liabilities and" in line:
            cy_liab_equity = cy
    if not seen_assets_total or cy_liab_equity == 0:
        return True, 0.0
    diff = cy_assets - cy_liab_equity
    return abs(diff) < 0.5, diff


def render_functional_expenses_tab():
    st.markdown(f"### {STATEMENT_FUNCTIONAL_EXPENSES}")
    st.caption("Matrix table — rows are expense categories, columns are programs/functions.")
    rows = st.session_state.statements.get(STATEMENT_FUNCTIONAL_EXPENSES, []) or seed_functional_expenses()
    df = pd.DataFrame(rows)
    column_config = {"line_item": st.column_config.TextColumn("Expense Category"), "level": None, "kind": None}
    for p in FUNCTIONAL_EXPENSES_PROGRAMS + ["Total"]:
        column_config[p] = st.column_config.NumberColumn(p, format="$%.2f")
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                             column_config=column_config, key="functional_expenses_editor", hide_index=True)
    if st.button("Recalculate Totals", key="recalc_functional"):
        for i, _ in edited.iterrows():
            edited.at[i, "Total"] = sum(float(edited.at[i, p] or 0) for p in FUNCTIONAL_EXPENSES_PROGRAMS)
        st.session_state.statements[STATEMENT_FUNCTIONAL_EXPENSES] = edited.to_dict(orient="records")
        st.success("Totals recalculated.")
        st.rerun()
    st.session_state.statements[STATEMENT_FUNCTIONAL_EXPENSES] = edited.to_dict(orient="records")


def render_standard_statement_tab(stmt_name):
    st.markdown(f"### {stmt_name}")
    rows = st.session_state.statements.get(stmt_name, []) or seed_statement_from_template(stmt_name)
    df = pd.DataFrame(rows)
    df_display = df.copy()
    if "level" in df_display.columns:
        df_display["line_item"] = df_display.apply(
            lambda r: ("    " * int(r.get("level") or 0)) + str(r.get("line_item", "")), axis=1)
    column_config = {
        "line_item": st.column_config.TextColumn("Line Item"),
        "cy_balance": st.column_config.NumberColumn("Current Year", format="$%.2f"),
        "py_balance": st.column_config.NumberColumn("Prior Year", format="$%.2f"),
        "level": st.column_config.NumberColumn("Indent Level", min_value=0, max_value=3, step=1),
        "kind": st.column_config.SelectboxColumn("Row Type", options=["line", "subtotal", "total", "header"]),
    }
    edited = st.data_editor(df_display, num_rows="dynamic", use_container_width=True,
                             column_config=column_config, key=f"editor_{stmt_name}", hide_index=True)
    edited["line_item"] = edited["line_item"].astype(str).str.lstrip()

    cols = st.columns([1, 1, 6])
    with cols[0]:
        if st.button("Recalculate Totals", key=f"recalc_{stmt_name}"):
            recomputed = recalculate_subtotals(edited.to_dict(orient="records"))
            st.session_state.statements[stmt_name] = recomputed
            st.success("Subtotals and totals recalculated.")
            st.rerun()
    with cols[1]:
        if st.button("Reseed from template", key=f"reseed_{stmt_name}"):
            st.session_state.statements[stmt_name] = seed_statement_from_template(stmt_name)
            st.success("Reseeded from standard template.")
            st.rerun()

    st.session_state.statements[stmt_name] = edited.to_dict(orient="records")

    if stmt_name in (STATEMENT_BALANCE_SHEET, STATEMENT_FINANCIAL_POSITION):
        ok, diff = balance_check_balance_sheet(st.session_state.statements[stmt_name])
        if not ok:
            st.error(f"⚠ Out of balance: Assets vs. Liabilities + Equity differ by ${diff:,.2f}.")
        else:
            st.success("Balance sheet balances.")


def page_statements():
    st.title("Financial Statements")
    if not st.session_state.statements_selected:
        st.warning("Select statements to prepare on the Upload page first.")
        return
    ensure_statements_seeded()
    render_checklist_sidebar(key_suffix="s")
    tabs = st.tabs(st.session_state.statements_selected)
    for tab, stmt_name in zip(tabs, st.session_state.statements_selected):
        with tab:
            if stmt_name == STATEMENT_FUNCTIONAL_EXPENSES:
                render_functional_expenses_tab()
            else:
                render_standard_statement_tab(stmt_name)
    st.info("Continue to **Notes** in the sidebar to draft disclosures.")


# =============================================================================
# PAGE: NOTES
# =============================================================================

def regen_note(idx, mode, instruction=""):
    note = st.session_state.notes[idx]
    with st.spinner("Regenerating note..."):
        try:
            updated = regenerate_note(
                provider=st.session_state.provider,
                api_key=st.session_state.api_key,
                entity_name=st.session_state.entity_name or "the Entity",
                entity_type=st.session_state.entity_type,
                note_title=note.get("title", ""),
                statements_summary=build_statements_summary(),
                instruction=instruction, mode=mode,
                existing_narrative=note.get("narrative", ""),
            )
        except Exception as e:
            st.error(f"Regeneration failed: {e}")
            return
    st.session_state.notes[idx] = updated
    st.success("Note regenerated.")
    st.rerun()


def render_note_card(idx, note):
    title = note.get("title", f"Note {idx + 1}")
    with st.expander(title, expanded=(idx == 0)):
        new_title = st.text_input("Note title", value=title, key=f"note_title_{idx}")
        new_narrative = st.text_area("Narrative", value=note.get("narrative", ""),
                                      key=f"note_narrative_{idx}", height=300)
        table_data = note.get("table_data") or []
        table_columns = note.get("table_columns") or []
        if table_columns:
            df = pd.DataFrame(table_data, columns=table_columns)
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                     key=f"note_table_{idx}", hide_index=True)
            note["table_data"] = edited.to_dict(orient="records")
            note["table_columns"] = list(edited.columns)
        elif table_data:
            cols = list(table_data[0].keys()) if table_data else []
            df = pd.DataFrame(table_data, columns=cols)
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True,
                                     key=f"note_table_{idx}", hide_index=True)
            note["table_data"] = edited.to_dict(orient="records")
            note["table_columns"] = list(edited.columns)

        note["title"] = new_title
        note["narrative"] = new_narrative

        cols = st.columns([1, 1, 1, 1, 4])
        with cols[0]:
            if st.button("🔄 Redo", key=f"redo_{idx}"):
                regen_note(idx, mode="redo")
        with cols[1]:
            if st.button("➕ Expand", key=f"expand_{idx}"):
                regen_note(idx, mode="expand")
        with cols[2]:
            with st.popover("✏️ Edit Prompt"):
                instr = st.text_area("Custom instruction", key=f"prompt_{idx}",
                                      placeholder="e.g., 'Add ASC 326 CECL disclosures.'")
                if st.button("Apply instruction", key=f"apply_prompt_{idx}"):
                    regen_note(idx, mode="custom", instruction=instr)
        with cols[3]:
            if st.button("🗑 Delete", key=f"del_{idx}"):
                st.session_state.notes.pop(idx)
                st.rerun()


def page_notes():
    st.title("Notes & Disclosures")
    if not st.session_state.statements:
        st.warning("Build your financial statements first on the Statements page.")
        return
    render_checklist_sidebar(key_suffix="n")

    left, right = st.columns([3, 1])
    with left:
        if not st.session_state.notes:
            st.info("No notes drafted yet. Click below to generate the initial draft.")
            if st.button("Generate initial notes", type="primary"):
                titles = required_note_titles(st.session_state.checklist) or [
                    "Summary of Significant Accounting Policies",
                    "Nature of Operations", "Subsequent Events",
                ]
                with st.spinner("Drafting notes — this may take a moment..."):
                    try:
                        notes = generate_all_notes(
                            provider=st.session_state.provider,
                            api_key=st.session_state.api_key,
                            entity_name=st.session_state.entity_name or "the Entity",
                            entity_type=st.session_state.entity_type,
                            fiscal_year_end=str(st.session_state.fiscal_year_end or ""),
                            statements_summary=build_statements_summary(),
                            required_notes=titles,
                            prior_year_notes_text=st.session_state.py_notes_text or "",
                        )
                    except Exception as e:
                        st.error(f"Note generation failed: {e}")
                        return
                if not notes:
                    st.error("The LLM did not return any notes. Try again or adjust the checklist.")
                    return
                sigacct_idx = next((i for i, n in enumerate(notes) if "significant accounting" in n.get("title", "").lower()), None)
                if sigacct_idx is None:
                    notes.insert(0, {
                        "title": "Note 1 - Summary of Significant Accounting Policies",
                        "narrative": "[CONFIRM: Significant accounting policies disclosure was not generated.]",
                        "table_data": [], "table_columns": [],
                    })
                elif sigacct_idx != 0:
                    note = notes.pop(sigacct_idx)
                    notes.insert(0, note)
                st.session_state.notes = notes
                st.success(f"Drafted {len(notes)} notes.")
                st.rerun()

        if st.session_state.notes:
            for idx, note in enumerate(st.session_state.notes):
                render_note_card(idx, note)

        st.divider()
        with st.expander("➕ Add a new note"):
            topic = st.selectbox("Standard GAAP disclosure", ["(custom topic)"] + STANDARD_NOTE_CATALOG)
            custom_topic = ""
            if topic == "(custom topic)":
                custom_topic = st.text_input("Custom note topic")
            if st.button("Generate note"):
                chosen = custom_topic if topic == "(custom topic)" else topic
                if not chosen:
                    st.error("Choose or enter a topic first.")
                    return
                with st.spinner("Generating note..."):
                    try:
                        new_note = generate_single_note(
                            provider=st.session_state.provider,
                            api_key=st.session_state.api_key,
                            entity_name=st.session_state.entity_name or "the Entity",
                            entity_type=st.session_state.entity_type,
                            note_topic=chosen, statements_summary=build_statements_summary(),
                        )
                    except Exception as e:
                        st.error(f"Generation failed: {e}")
                        return
                st.session_state.notes.append(new_note)
                st.success(f"Added note: {new_note.get('title', chosen)}")
                st.rerun()
    with right:
        st.markdown("**Tips**")
        st.caption("• Use **Redo** for a fresh take, **Expand** to add depth, **Edit Prompt** for surgical edits.")
        st.caption("• `[CONFIRM: ...]` markers flag figures the AI couldn't derive — fill them in before exporting.")
        st.caption("• Note 1 is always Summary of Significant Accounting Policies.")
    st.info("Continue to **Export** when notes are ready.")


# =============================================================================
# PAGE: EXPORT
# =============================================================================

def safe_filename(text):
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text or "")
    return cleaned.strip("_") or "Entity"


def page_export():
    st.title("Export")
    st.caption("Final review before generating the deliverable.")
    if not st.session_state.statements:
        st.warning("Build your statements before exporting.")
        return

    st.subheader("GAAP Disclosure Checklist — pre-export review")
    checklist = st.session_state.checklist or []
    if not checklist:
        st.info("No checklist generated yet. Visit Statements or Notes first.")
        return

    completed, total = progress_counts(checklist)
    st.progress((completed / total) if total else 1.0, text=f"{completed} of {total} required disclosures complete")

    incomplete_required = [c for c in checklist if c.get("status") == REQUIRED and not c.get("complete")]
    can_proceed = True
    if incomplete_required:
        st.error(f"⚠ {len(incomplete_required)} required disclosure(s) are not marked complete.")
        for c in incomplete_required:
            st.markdown(f"- **{c.get('title')}** ({c.get('category')})")
        can_proceed = st.checkbox("I acknowledge incomplete disclosures and want to export anyway.", key="ack_incomplete")
    else:
        st.success("All required disclosures are marked complete.")

    st.divider()
    if not can_proceed:
        st.warning("Acknowledge above to enable downloads.")
        return

    st.subheader("Download")
    entity_name = st.session_state.entity_name or "Entity"
    fye_str = str(st.session_state.fiscal_year_end or "FYE")
    safe_entity = safe_filename(entity_name)
    safe_fye = safe_filename(fye_str)

    include_checklist = st.checkbox("Include GAAP Disclosure Checklist appendix in PDF", value=False)

    cols = st.columns(2)
    with cols[0]:
        if st.button("Generate PDF", type="primary"):
            with st.spinner("Building PDF..."):
                try:
                    pdf_bytes = build_pdf(
                        entity_name=entity_name, entity_type=st.session_state.entity_type,
                        fiscal_year_end=fye_str, statements=st.session_state.statements or {},
                        notes=st.session_state.notes or [], checklist=st.session_state.checklist or [],
                        include_checklist_appendix=include_checklist,
                    )
                except Exception as e:
                    st.error(f"PDF build failed: {e}")
                    return
            st.session_state["_pdf_bytes"] = pdf_bytes
            st.success("PDF ready.")

        if st.session_state.get("_pdf_bytes"):
            st.download_button(
                "📄 Download Financial Statements PDF",
                data=st.session_state["_pdf_bytes"],
                file_name=f"{safe_entity}_FinancialStatements_{safe_fye}.pdf",
                mime="application/pdf",
            )

    with cols[1]:
        if st.button("Generate session workbook"):
            with st.spinner("Building Excel workbook..."):
                try:
                    xlsx_bytes = build_session_excel(
                        parsed_tb=st.session_state.parsed_tb,
                        statements=st.session_state.statements or {},
                        notes=st.session_state.notes or [],
                    )
                except Exception as e:
                    st.error(f"Workbook build failed: {e}")
                    return
            st.session_state["_xlsx_bytes"] = xlsx_bytes
            st.success("Workbook ready.")

        if st.session_state.get("_xlsx_bytes"):
            st.download_button(
                "📊 Download session workbook (re-uploadable)",
                data=st.session_state["_xlsx_bytes"],
                file_name=f"{safe_entity}_SessionData_{safe_fye}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


# =============================================================================
# HOME PAGE + ROUTER
# =============================================================================

def page_home():
    st.title("FinStatement AI")
    st.caption("AI-assisted preparation of GAAP-compliant financial statements (FASB and ASC 958)")
    st.markdown("""
### Workflow

1. **Upload** — set entity details and upload either a prior-year FS or a current-year trial balance.
2. **Statements** — review, edit, and balance the financial statements selected for this engagement.
3. **Notes** — review AI-drafted notes; redo, expand, or apply custom edits as needed.
4. **Export** — download the assembled PDF and a re-uploadable session workbook.

Use **Reset Session** in the sidebar to clear all data and start over.
""")


def render_api_key_gate():
    st.sidebar.header("LLM provider")
    if st.session_state.api_key_validated:
        provider_label = PROVIDER_LABELS.get(st.session_state.provider, st.session_state.provider)
        st.sidebar.success(f"{provider_label} validated")
        if st.sidebar.button("Change provider / API key"):
            st.session_state.api_key = ""
            st.session_state.api_key_validated = False
            st.rerun()
        return True

    provider_choice = st.sidebar.radio(
        "Choose a provider",
        [PROVIDER_ANTHROPIC, PROVIDER_OPENAI],
        format_func=lambda p: PROVIDER_LABELS[p],
        index=[PROVIDER_ANTHROPIC, PROVIDER_OPENAI].index(st.session_state.provider),
    )
    st.session_state.provider = provider_choice

    key_input = st.sidebar.text_input(
        f"Enter your {PROVIDER_LABELS[provider_choice]} API key",
        type="password", value=st.session_state.api_key,
        help=PROVIDER_HELP[provider_choice] + ". The key is held in session state and never written to disk.",
    )
    if st.sidebar.button("Validate key", type="primary", disabled=not key_input):
        with st.spinner(f"Validating {PROVIDER_LABELS[provider_choice]} API key..."):
            ok, msg = validate_api_key(provider_choice, key_input)
        if ok:
            st.session_state.api_key = key_input.strip()
            st.session_state.api_key_validated = True
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)
    return False


def render_sidebar_nav():
    st.sidebar.divider()
    st.sidebar.subheader("Navigation")
    pages = ["Home", "Upload", "Statements", "Notes", "Export"]
    current = st.session_state.get("current_page", "Home")
    if current not in pages:
        current = "Home"
    selected = st.sidebar.radio("Page", pages, index=pages.index(current), label_visibility="collapsed")
    st.session_state.current_page = selected

    st.sidebar.divider()
    st.sidebar.subheader("Session")
    if st.sidebar.button("Reset Session"):
        reset_session()
        st.rerun()
    st.sidebar.caption(f"Provider: {PROVIDER_LABELS.get(st.session_state.provider, st.session_state.provider)}")
    st.sidebar.caption(f"Entity: {st.session_state.entity_name or '(not set)'}")
    st.sidebar.caption(f"Type: {st.session_state.entity_type}")
    return selected


def main():
    init_session_state()
    if not render_api_key_gate():
        st.title("FinStatement AI")
        st.info("Enter your Anthropic API key in the sidebar to begin.")
        return
    page = render_sidebar_nav()
    if page == "Home":
        page_home()
    elif page == "Upload":
        page_upload()
    elif page == "Statements":
        page_statements()
    elif page == "Notes":
        page_notes()
    elif page == "Export":
        page_export()


main()
