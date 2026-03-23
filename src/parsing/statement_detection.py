from __future__ import annotations


STATEMENT_KEYWORDS = {
    "statement of financial position": "balance_sheet",
    "balance sheet": "balance_sheet",
    "statement of activities": "activities",
    "statement of functional expenses": "functional_expenses",
    "statement of cash flows": "cash_flows",
    "notes to": "notes",
}


def detect_statement_name(page_text: str) -> str:
    lowered = page_text.lower()
    for phrase, label in STATEMENT_KEYWORDS.items():
        if phrase in lowered:
            return label
    return "unknown"
