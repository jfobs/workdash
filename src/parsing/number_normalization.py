from __future__ import annotations

import re


_NUM_RE = re.compile(r"^[\(\-]?\$?[\d,]+(?:\.\d+)?\)?%?$")


def looks_numeric(text: str) -> bool:
    token = text.strip().replace("−", "-")
    if token in {"", "-", "—", "–"}:
        return False
    return bool(_NUM_RE.match(token))


def normalize_numeric(text: str) -> float | None:
    raw = text.strip().replace("−", "-")
    if raw in {"", "-", "—", "–", "n/a", "N/A"}:
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    pct = raw.endswith("%")
    cleaned = raw.strip("()%$").replace(",", "")
    if cleaned in {"", "-"}:
        return None
    value = float(cleaned)
    if negative:
        value = -value
    if pct:
        value /= 100.0
    return value
