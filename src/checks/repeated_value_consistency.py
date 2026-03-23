from __future__ import annotations

from collections import defaultdict
from uuid import uuid4

from src.storage.models import CheckResult, CheckStatus, NumericFact


def run_repeated_value_consistency(facts: list[NumericFact], tolerance: float = 1.0) -> list[CheckResult]:
    groups = defaultdict(list)
    for fact in facts:
        if fact.normalized_value is not None:
            groups[round(fact.normalized_value, 2)].append(fact)

    results: list[CheckResult] = []
    for _, items in groups.items():
        if len(items) < 2:
            continue
        results.append(
            CheckResult(
                result_id=f"res_{uuid4().hex}",
                check_id="repeated_value_consistency",
                status=CheckStatus.PASS,
                formula="same value appears in multiple places",
                narrative="Repeated-value consistency",
                source_fact_ids=[items[0].fact_id],
                target_fact_ids=[f.fact_id for f in items[1:]],
                tolerance=tolerance,
                calculated_difference=0.0,
                explanation="Identical numeric values found across sections",
            )
        )
    return results
