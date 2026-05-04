"""Centralized LLM API wrappers for FinStatement AI.

Supports both Anthropic (Claude) and OpenAI as drop-in providers. The
high-level note/mapping functions take a `provider` argument; the
private `_call_llm` helper dispatches to the right SDK.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import anthropic
import openai
import pandas as pd


PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_OPENAI = "openai"
SUPPORTED_PROVIDERS = (PROVIDER_ANTHROPIC, PROVIDER_OPENAI)

# Active aliases. Override in session state if desired.
DEFAULT_MODEL_ANTHROPIC = "claude-sonnet-4-5"
DEFAULT_MODEL_OPENAI = "gpt-4o"


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


# ---------------------------------------------------------------------------
# Provider dispatch
# ---------------------------------------------------------------------------

def _call_llm(
    provider: str,
    api_key: str,
    system: str,
    user_prompt: str,
    max_tokens: int,
    want_json: bool = False,
    model_override: Optional[str] = None,
) -> str:
    """Call the configured LLM provider and return the response text."""
    if provider == PROVIDER_OPENAI:
        return _call_openai(api_key, system, user_prompt, max_tokens, want_json, model_override)
    return _call_anthropic(api_key, system, user_prompt, max_tokens, model_override)


def _call_anthropic(api_key, system, user_prompt, max_tokens, model_override=None) -> str:
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


def _call_openai(api_key, system, user_prompt, max_tokens, want_json=False, model_override=None) -> str:
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


# ---------------------------------------------------------------------------
# JSON extraction (works for both providers)
# ---------------------------------------------------------------------------

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


def _extract_json(text: str):
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


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------

def validate_api_key(provider: str, api_key: str) -> tuple[bool, str]:
    """Cheap test call to confirm the key works. Returns (ok, message)."""
    if provider not in SUPPORTED_PROVIDERS:
        return False, f"Unsupported provider: {provider}"
    if not api_key or not api_key.strip():
        return False, "API key is empty."
    try:
        if provider == PROVIDER_OPENAI:
            client = openai.OpenAI(api_key=api_key.strip())
            client.chat.completions.create(
                model=DEFAULT_MODEL_OPENAI,
                max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
        else:
            client = anthropic.Anthropic(api_key=api_key.strip())
            client.messages.create(
                model=DEFAULT_MODEL_ANTHROPIC,
                max_tokens=8,
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
        return False, f"Unexpected error validating key: {e}"


# ---------------------------------------------------------------------------
# Account mapping suggestion
# ---------------------------------------------------------------------------

def suggest_account_mapping(
    provider: str,
    api_key: str,
    accounts_df: pd.DataFrame,
    entity_type: str,
) -> pd.DataFrame:
    """Ask the LLM to assign GAAP statement, group, and line_item to each account."""
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

Return ONLY a JSON object with key "accounts" mapping to an array. Each array \
element MUST have keys: account_number, account_description, statement, group, line_item.

Accounts to classify:
{json.dumps(rows, indent=2)}
"""

    text = _call_llm(
        provider=provider,
        api_key=api_key,
        system="You are an expert CPA classifying chart-of-accounts entries to GAAP financial statement line items. Return strict JSON only.",
        user_prompt=user_prompt,
        max_tokens=8000,
        want_json=True,
    )
    parsed = _extract_json(text)
    # Accept either {"accounts": [...]} (preferred for OpenAI json_object) or a bare array.
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
        if match.get("statement"):
            out.at[idx, "statement"] = match["statement"]
        if match.get("group"):
            out.at[idx, "group"] = match["group"]
        if match.get("line_item"):
            out.at[idx, "line_item"] = match["line_item"]
    return out


# ---------------------------------------------------------------------------
# Note generation
# ---------------------------------------------------------------------------

def generate_all_notes(
    provider: str,
    api_key: str,
    entity_name: str,
    entity_type: str,
    fiscal_year_end: str,
    statements_summary: dict,
    required_notes: list[str],
    prior_year_notes_text: str = "",
) -> list[dict]:
    """Generate the full initial set of notes in one call."""
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
Return ONLY a JSON object with key "notes" mapping to an array. Each array \
element MUST have these keys:
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

    text = _call_llm(
        provider=provider,
        api_key=api_key,
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


def regenerate_note(
    provider: str,
    api_key: str,
    entity_name: str,
    entity_type: str,
    note_title: str,
    statements_summary: dict,
    instruction: str = "",
    mode: str = "redo",
    existing_narrative: str = "",
) -> dict:
    """Regenerate a single note: redo from scratch, expand, or apply a custom instruction."""
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

    text = _call_llm(
        provider=provider,
        api_key=api_key,
        system=SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type),
        user_prompt=user_prompt,
        max_tokens=6000,
        want_json=True,
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


def generate_single_note(
    provider: str,
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

    text = _call_llm(
        provider=provider,
        api_key=api_key,
        system=SYSTEM_NOTE_DRAFTER.format(entity_type=entity_type),
        user_prompt=user_prompt,
        max_tokens=4000,
        want_json=True,
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
