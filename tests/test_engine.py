from datetime import date
from decimal import Decimal

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from disclosures import maturity_analysis
from lease_engine import build_payment_stream, consolidate_schedules, generate_lease_schedule, pv_of_lease_payments
from models import LeaseInput


def mk_lease(classification="finance", timing="EOM"):
    return LeaseInput(
        lease_id="L1",
        lease_name="Test",
        classification=classification,
        commencement_date=date(2024, 1, 1),
        payment_amount=Decimal("1000"),
        payment_timing=timing,
        lease_term_months=12,
        annual_discount_rate=Decimal("0.12"),
    )


def test_pv_math():
    pv = pv_of_lease_payments(Decimal("1000"), Decimal("0.01"), 12, "EOM")
    assert round(float(pv), 2) == 11255.08


def test_finance_schedule_end_near_zero():
    df = generate_lease_schedule(mk_lease("finance", "EOM"))
    assert abs(df["end_liability"].iloc[-1]) <= 0.01


def test_operating_single_cost_behavior():
    df = generate_lease_schedule(mk_lease("operating", "EOM"))
    assert df["lease_expense"].nunique() == 1


def test_bom_vs_eom_differs():
    eom = generate_lease_schedule(mk_lease("finance", "EOM"))
    bom = generate_lease_schedule(mk_lease("finance", "BOM"))
    assert bom["interest_expense"].sum() < eom["interest_expense"].sum()


def test_disclosure_maturity_totals():
    df = generate_lease_schedule(mk_lease("finance", "EOM"))
    m = maturity_analysis(df, date(2024, 12, 31))
    total_row = m[m["Label"] == "Total undiscounted cash flows"].iloc[0]
    assert total_row["Finance"] >= 0


def test_consolidation_sums():
    d1 = generate_lease_schedule(mk_lease("finance", "EOM"))
    l2 = mk_lease("operating", "EOM")
    l2.lease_id = "L2"
    d2 = generate_lease_schedule(l2)
    c = consolidate_schedules([d1, d2])
    assert round(c["payment"].sum(), 2) == round(d1["payment"].sum() + d2["payment"].sum(), 2)


def test_escalation_payment_stream_steps_up_annually():
    lease = mk_lease("operating", "EOM")
    lease.lease_term_months = 24
    lease.escalation_rate_annual = Decimal("0.10")
    lease.escalation_interval_months = 12
    stream = build_payment_stream(lease)
    assert stream[0] == Decimal("1000")
    assert stream[12] == Decimal("1100")


def test_explicit_rent_steps_override_escalation():
    lease = mk_lease("operating", "EOM")
    lease.lease_term_months = 24
    lease.escalation_rate_annual = Decimal("0.10")
    lease.rent_steps_json = '{"1": 1000, "13": 1300}'
    stream = build_payment_stream(lease)
    assert stream[12] == Decimal("1300")


def test_pdf_extraction_requires_api_key(monkeypatch):
    from ai.pdf_ingest import extract_leases_from_pdf

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        extract_leases_from_pdf(b"%PDF-1.4\n%fake")
    except RuntimeError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when key missing")


def test_pdf_normalize_keeps_usable_rows():
    from ai.pdf_ingest import _normalize_extracted_rows

    rows = [
        {"lease_name": "X", "payment_amount": 2500, "lease_term_months": 60},
        {"lease_name": "Y", "payment_amount": None, "lease_term_months": 24},
    ]
    norm = _normalize_extracted_rows(rows)
    assert len(norm) == 1
    assert norm[0]["payment_amount"] == 2500.0


def test_pdf_fallback_extracts_amount_and_term():
    from ai.pdf_ingest import _fallback_lease_from_text

    text = "Base rent is $2,500 per month for an initial term of 5 years."
    fallback = _fallback_lease_from_text(text)
    assert fallback is not None
    assert fallback["payment_amount"] == 2500.0
    assert fallback["lease_term_months"] == 60


def test_pdf_extract_json_from_text_fenced():
    from ai.pdf_ingest import _extract_json_from_text

    raw = "```json\n{\"leases\":[{\"payment_amount\":2500,\"lease_term_months\":60}]}\n```"
    rows = _extract_json_from_text(raw)
    assert len(rows) == 1
    assert rows[0]["lease_term_months"] == 60
