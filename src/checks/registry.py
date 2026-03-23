from __future__ import annotations

from src.checks.cross_statement import run_cross_statement_ties
from src.checks.footing import run_row_and_column_footing
from src.checks.note_links import run_note_links
from src.checks.repeated_value_consistency import run_repeated_value_consistency
from src.checks.rollforward import run_rollforward
from src.storage.models import CheckResult, NumericFact


def run_all_checks(facts: list[NumericFact], tolerance: float = 1.0) -> list[CheckResult]:
    results: list[CheckResult] = []
    for check_fn in (
        run_row_and_column_footing,
        run_rollforward,
        run_cross_statement_ties,
        run_note_links,
        run_repeated_value_consistency,
    ):
        results.extend(check_fn(facts, tolerance=tolerance))
    return results
