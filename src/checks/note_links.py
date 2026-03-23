from __future__ import annotations

from uuid import uuid4

from src.storage.models import CheckResult, CheckStatus, NumericFact


def run_note_links(facts: list[NumericFact], tolerance: float = 1.0) -> list[CheckResult]:
    notes = [f for f in facts if f.source_type == "note" and f.normalized_value is not None]
    face = [f for f in facts if f.source_type != "note" and f.normalized_value is not None]
    results: list[CheckResult] = []
    for note in notes:
        best = min(face, key=lambda x: abs((x.normalized_value or 0) - (note.normalized_value or 0)), default=None)
        if best is None:
            continue
        diff = abs((best.normalized_value or 0) - (note.normalized_value or 0))
        status = CheckStatus.PASS if diff <= tolerance else CheckStatus.UNREVIEWED
        results.append(
            CheckResult(
                result_id=f"res_{uuid4().hex}",
                check_id="note_face_link",
                status=status,
                formula="note total == face statement balance",
                narrative="Note detail tie",
                source_fact_ids=[note.fact_id],
                target_fact_ids=[best.fact_id],
                tolerance=tolerance,
                calculated_difference=diff,
                explanation="Best deterministic tie candidate from notes to face statements",
            )
        )
    return results
