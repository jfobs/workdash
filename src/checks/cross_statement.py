from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from src.storage.models import CheckResult, CheckStatus, NumericFact


def run_cross_statement_ties(facts: list[NumericFact], tolerance: float = 1.0) -> list[CheckResult]:
    by_period = defaultdict(list)
    for fact in facts:
        if fact.normalized_value is not None:
            by_period[fact.period_label or "unknown"].append(fact)

    results: list[CheckResult] = []
    for period, items in by_period.items():
        if len(items) < 2:
            continue
        left = items[0]
        for right in items[1:]:
            if left.statement_name == right.statement_name:
                continue
            diff = abs((left.normalized_value or 0) - (right.normalized_value or 0))
            status = CheckStatus.PASS if diff <= tolerance else CheckStatus.WARNING
            results.append(
                CheckResult(
                    result_id=f"res_{uuid4().hex}",
                    check_id="cross_statement_equality",
                    status=status,
                    formula="left == right",
                    narrative=f"Cross statement tie candidate ({period})",
                    source_fact_ids=[left.fact_id],
                    target_fact_ids=[right.fact_id],
                    tolerance=tolerance,
                    calculated_difference=diff,
                    explanation="Potential cross-statement tie based on period and extracted value",
                )
            )
    return results
