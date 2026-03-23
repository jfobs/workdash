from src.checks.registry import run_all_checks
from src.storage.models import NumericFact


def _fact(fid: str, statement: str, value: float, source_type: str = "face_statement") -> NumericFact:
    return NumericFact(
        fact_id=fid,
        document_id="doc1",
        page_number=1,
        statement_name=statement,
        table_name=None,
        row_label=None,
        column_label=None,
        period_label="2025",
        raw_text=str(value),
        normalized_value=value,
        bbox=(0, 0, 1, 1),
        extraction_confidence=1.0,
        source_type=source_type,
    )


def test_registry_returns_results():
    facts = [
        _fact("a", "activities", 100),
        _fact("b", "activities", 50),
        _fact("c", "activities", 150),
        _fact("d", "balance_sheet", 150),
        _fact("e", "notes", 150, source_type="note"),
    ]
    results = run_all_checks(facts)
    assert results
