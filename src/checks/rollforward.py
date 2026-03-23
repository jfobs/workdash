from __future__ import annotations

from uuid import uuid4

from src.storage.models import CheckResult, CheckStatus, NumericFact


def run_rollforward(facts: list[NumericFact], tolerance: float = 1.0) -> list[CheckResult]:
    values = [f for f in facts if f.statement_name == "activities" and f.normalized_value is not None]
    if len(values) < 3:
        return []
    beginning, change, ending = values[0], values[1], values[2]
    diff = abs((beginning.normalized_value + change.normalized_value) - ending.normalized_value)
    status = CheckStatus.PASS if diff <= tolerance else CheckStatus.FAIL
    return [
        CheckResult(
            result_id=f"res_{uuid4().hex}",
            check_id="rollforward",
            status=status,
            formula="beginning + change = ending",
            narrative="Statement of activities rollforward",
            source_fact_ids=[beginning.fact_id, change.fact_id],
            target_fact_ids=[ending.fact_id],
            tolerance=tolerance,
            calculated_difference=diff,
            explanation="Net asset rollforward check",
        )
    ]
