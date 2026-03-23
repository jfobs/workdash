from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExtractedWord:
    text: str
    bbox: tuple[float, float, float, float]


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    statement_name: str
    words: list[ExtractedWord]
