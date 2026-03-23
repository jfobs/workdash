from __future__ import annotations

from uuid import uuid4

import fitz

from src.parsing.number_normalization import looks_numeric, normalize_numeric
from src.parsing.statement_detection import detect_statement_name
from src.storage.models import NumericFact


def extract_numeric_facts(pdf_bytes: bytes, document_id: str) -> list[NumericFact]:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    facts: list[NumericFact] = []
    for page_idx, page in enumerate(doc):
        words = page.get_text("words")
        page_text = page.get_text("text")
        statement_name = detect_statement_name(page_text)
        year_tokens = [w[4] for w in words if str(w[4]).isdigit() and len(str(w[4])) == 4]
        period_label = year_tokens[0] if year_tokens else None
        for word in words:
            text = str(word[4]).strip()
            if not looks_numeric(text):
                continue
            value = normalize_numeric(text)
            facts.append(
                NumericFact(
                    fact_id=f"fact_{uuid4().hex}",
                    document_id=document_id,
                    page_number=page_idx + 1,
                    statement_name=statement_name,
                    table_name="detected_table",
                    row_label=None,
                    column_label=None,
                    period_label=period_label,
                    raw_text=text,
                    normalized_value=value,
                    bbox=(float(word[0]), float(word[1]), float(word[2]), float(word[3])),
                    extraction_confidence=0.95,
                    source_type="face_statement" if statement_name != "notes" else "note",
                )
            )
    return facts
