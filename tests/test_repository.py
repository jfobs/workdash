from src.storage.models import CheckResult, CheckStatus
from src.storage.repository import Repository


def test_repository_roundtrip(tmp_path):
    repo = Repository(str(tmp_path / "test.db"))
    result = CheckResult(
        result_id="r1",
        check_id="c1",
        status=CheckStatus.PASS,
        formula="1+1=2",
        narrative="n",
        source_fact_ids=["f1"],
        target_fact_ids=["f2"],
        tolerance=1,
        calculated_difference=0,
        explanation="ok",
    )
    repo.upsert_results([result])
    loaded = repo.list_results()
    assert loaded[0].result_id == "r1"
