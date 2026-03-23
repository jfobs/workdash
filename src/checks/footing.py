from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from src.storage.models import CheckResult, CheckStatus, NumericFact


def run_row_and_column_footing(facts: list[NumericFact], tolerance: float = 1.0) -> list[CheckResult]:
    grouped: dict[tuple[str, int, str], list[NumericFact]] = defaultdict(list)
    for fact in facts:
        if fact.normalized_value is None:
            continue
        grouped[(fact.statement_name, fact.page_number, fact.period_label or "")].append(fact)

    results: list[CheckResult] = []
    for key, bucket in grouped.items():
        if len(bucket) < 3:
            continue
        values = sorted([f.normalized_value for f in bucket if f.normalized_value is not None])
        if len(values) < 3:
            continue
        calc = sum(values[:-1])
        target = values[-1]
        diff = abs(calc - target)
        status = CheckStatus.PASS if diff <= tolerance else CheckStatus.FAIL
        results.append(
            CheckResult(
                result_id=f"res_{uuid4().hex}",
                check_id="row_column_footing",
                status=status,
                formula="sum(values[:-1]) == values[-1]",
                narrative=f"Footing check for {key[0]} page {key[1]}",
                source_fact_ids=[f.fact_id for f in bucket[:-1]],
                target_fact_ids=[bucket[-1].fact_id],
                tolerance=tolerance,
                calculated_difference=diff,
                explanation="Automated deterministic footing check",
            )
        )
    return results
