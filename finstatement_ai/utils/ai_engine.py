"""Centralized Claude API wrappers for FinStatement AI.

All Claude calls live here. Pages call high-level helpers; this module
handles prompt construction, JSON parsing, and error surfacing.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import anthropic
import pandas as pd


# Active Sonnet alias. The original spec named claude-sonnet-4-20250514, which
# is the deprecated Sonnet 4.0 release; claude-sonnet-4-5 is its drop-in
# replacement and remains active. Bump to claude-sonnet-4-6 when ready.
DEFAULT_MODEL = "claude-sonnet-4-5"


SYSTEM_NOTE_DRAFTER = """You are an expert CPA and technical accounting writer drafting GAAP-compliant \
notes to financial statements for {entity_type} entities under U.S. GAAP \
(FASB ASC, including ASC 958 for nonprofits).

Requirements:
- Write in formal, third-person accounting disclosure language.
- Reference the actual dollar amounts you are given. Do not fabricate figures.
- Where a fact is required for the disclosure but is missing from the data \
(e.g., effective interest rate, lease term, useful lives), insert a placeholder \
in the form [CONFIRM: <what to confirm>].
- Use proper GAAP terminology (e.g., "without donor restrictions" / "with donor \
restrictions" for nonprofits; "Company" / "Organization" for the entity).
- Be concise but complete. Do not invent disclosures that are not warranted by \
the data.
- Follow standard ordering: Note 1 is always Summary of Significant Accounting Policies.
"""


def _client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def _extract_text(response) -> str:
    parts = []
    for block in response.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "".join(parts)


def _extract_json(text: str) -> Optional[dict | list]:
    """Pull a JSON object/array out of model output. Tolerates code fences and prose."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else text.strip()
    # Try the whole candidate first; fall back to the first {...} or [...] block.
    for chunk in (candidate, _first_json_blob(candidate)):
        if not chunk:
            continue
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    return None


def _first_json_blob(text: str) -> Optional[str]:
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


def validate_api_key(api_key: str) -> tuple[bool, str]:
    """Cheap test call to confirm the key works. Returns (ok, message)."""
    if not api_key or not api_key.strip():
        return False, "API key is empty."
    try:
        client = _client(api_key.strip())
        client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=8,
            messages=[{"role": "user", "content": "ping"}],
        )
        return True, "API key validated."
    except anthropic.AuthenticationError:
        return False, "Invalid API key. Please check the key and try again."
    except anthropic.PermissionDeniedError:
        return False, "API key lacks permission to call this model."
    except anthropic.RateLimitError:
        return False, "Rate limited while validating. The key looks valid; try again in a moment."
    except anthropic.APIConnectionError:
        return False, "Could not reach the Anthropic API. Check your network."
    except Exception as e:
        return False, f"Unexpected error validating key: {e}"


def suggest_account_mapping(api_key: str, accounts_df: pd.DataFrame, entity_type: str) -> pd.DataFrame:
    """Ask Claude to assign GAAP statement, group, and line_item to each account.

    Returns the input dataframe with `statement`, `group`, and `line_item`
    populated where the model could classify them.
    """
    if accounts_df is None or accounts_df.empty:
        return accounts_df

    rows = []
    for _, row in accounts_df.iterrows():
        rows.append({
            "account_number": str(row.get("account_number", "")),
            "account_description": str(row.get("account_description", "")),
            "cy_balance": float(row.get("cy_balance", 0) or 0),
        })

    user_prompt = f"""You are mapping a chart of accounts to GAAP financial statement \
line items for a {entity_type} entity.

For each account, return:
- statement: one of "Balance Sheet", "Income Statement", "Cash Flow Statement", \
"Statement of Activities", "Statement of Financial Position"
- group: e.g. "Assets", "Liabilities", "Equity", "Revenue", "Operating Expenses", \
"Net Assets Without Donor Restrictions", "Net Assets With Donor Restrictions"
- line_item: a standard GAAP caption (e.g., "Cash and cash equivalents", \
"Accounts receivable, net", "Long-term debt, net of current portion")

Return ONLY a JSON array. Each element MUST have keys: account_number, \
account_description, statement, group, line_item.

Accounts to classify:
{json.dumps(rows, indent=2)}
"""

    client = _client(api_key)
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=8000,
        system="You are an expert CPA classifying chart-of-accounts entries to GAAP financial statement line items. Return strict JSON only.",
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = _extract_text(response)
    parsed = _extract_json(text)
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
        if match.get("statement"):
            out.at[idx, "statement"] = match["statement"]
        if match.get("group"):
            out.at[idx, "group"] = match["group"]
        if match.get("line_item"):
            out.at[idx, "line_item"] = match["line_item"]
    return out


def generate_all_notes(
    api_key: str,
    entity_name: str,
    entity_type: str,
    fiscal_year_end: str,
    statements_summary: dict,
    required_notes: list[str],
    prior_year_notes_text: str = "",
) -> list[dict]:
    """Generate the full initial set of notes in one call.

    Returns: list of dicts with keys: title, narrative, table_data (list of dicts | []), table_columns (list[str]).
    """
    pyn = ""
    if prior_year_notes_text:
        pyn = f"\nPrior year note language (use as a starting point; update figures to current year):\n{prior_year_notes_text[:6000]}\n"

    user_prompt = f"""Draft the full set of notes to financial statements for the following entity.

Entity: {entity_name}
Entity type: {entity_type}
Fiscal year end: {fiscal_year_end}

Financial statement summary (current and prior year amounts by line item):
{json.dumps(statements_summary, indent=2, default=str)}

Required notes (in order):
{json.dumps(required_notes, indent=2)}
{pyn}
Return ONLY a JSON array. Each element MUST have these keys:
- title: the note title (e.g., "Note 1 - Summary of Significant Accounting Policies")
- narrative: formal disclosure prose. Use real dollar figures from the data. \
Use [CONFIRM: ...] for any figure or fact you cannot derive from the data.
- table_data: an array of row objects (each row is a dict of column-name -> value). \
Use [] if no table is appropriate for this note.
- table_columns: an array of column names matching the keys in table_data, \
preserving display order. Use [] if table_data is [].

For notes that conventionally have a schedule (debt schedule, lease maturity, \
property and equipment, net asset rollforward, etc.), populate table_data and \
table_columns. Note 1 is always Summary of Significant Accounting Policies.
"""

    system = SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type)

    client = _client(api_key)
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = _extract_text(response)
    parsed = _extract_json(text)
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


def regenerate_note(
    api_key: str,
    entity_name: str,
    entity_type: str,
    note_title: str,
    statements_summary: dict,
    instruction: str = "",
    mode: str = "redo",
    existing_narrative: str = "",
) -> dict:
    """Regenerate a single note: redo from scratch, expand, or apply a custom instruction.

    mode: 'redo' | 'expand' | 'custom'
    """
    if mode == "redo":
        directive = "Generate this note from scratch, taking a different approach than before."
    elif mode == "expand":
        directive = ("Expand the existing note: add more detail, additional sub-sections, "
                     "and address all relevant GAAP requirements that may have been omitted.")
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

    system = SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type)
    client = _client(api_key)
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=6000,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = _extract_text(response)
    parsed = _extract_json(text)
    if not isinstance(parsed, dict):
        return {"title": note_title, "narrative": text.strip(), "table_data": [], "table_columns": []}
    return {
        "title": str(parsed.get("title", note_title)),
        "narrative": str(parsed.get("narrative", "")),
        "table_data": parsed.get("table_data") if isinstance(parsed.get("table_data"), list) else [],
        "table_columns": parsed.get("table_columns") if isinstance(parsed.get("table_columns"), list) else [],
    }


def generate_single_note(
    api_key: str,
    entity_name: str,
    entity_type: str,
    note_topic: str,
    statements_summary: dict,
) -> dict:
    """Generate a fresh single note for a specified GAAP topic."""
    user_prompt = f"""Draft a single GAAP-compliant note for the topic below.

Entity: {entity_name}
Entity type: {entity_type}
Note topic: {note_topic}

Financial statement summary:
{json.dumps(statements_summary, indent=2, default=str)}

Return ONLY a JSON object with keys: title, narrative, table_data, table_columns.
"""
    system = SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type)
    client = _client(api_key)
    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = _extract_text(response)
    parsed = _extract_json(text)
    if not isinstance(parsed, dict):
        return {"title": note_topic, "narrative": text.strip(), "table_data": [], "table_columns": []}
    return {
        "title": str(parsed.get("title", note_topic)),
        "narrative": str(parsed.get("narrative", "")),
        "table_data": parsed.get("table_data") if isinstance(parsed.get("table_data"), list) else [],
        "table_columns": parsed.get("table_columns") if isinstance(parsed.get("table_columns"), list) else [],
    }
