from __future__ import annotations

from uuid import uuid4

from src.storage.models import CalculatorSelection, NumericFact


def intersecting_facts(facts: list[NumericFact], bbox: tuple[float, float, float, float]) -> list[NumericFact]:
    x0, y0, x1, y1 = bbox

    def overlaps(a: tuple[float, float, float, float]) -> bool:
        ax0, ay0, ax1, ay1 = a
        return not (ax1 < x0 or x1 < ax0 or ay1 < y0 or y1 < ay0)

    return [f for f in facts if f.bbox and overlaps(f.bbox)]


def calculate_selection(
    document_id: str,
    page_number: int,
    bbox: tuple[float, float, float, float],
    selected_facts: list[NumericFact],
    signs: list[int],
    reviewer: str,
) -> CalculatorSelection:
    values = [f.normalized_value or 0.0 for f in selected_facts]
    total = sum(v * s for v, s in zip(values, signs, strict=False))
    return CalculatorSelection(
        selection_id=f"calc_{uuid4().hex}",
        document_id=document_id,
        page_number=page_number,
        bbox=bbox,
        ordered_fact_ids=[f.fact_id for f in selected_facts],
        signs=signs,
        result_value=total,
        reviewer=reviewer,
    )
