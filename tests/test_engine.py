from datetime import date
from decimal import Decimal

import pandas as pd

from disclosures import maturity_analysis
from lease_engine import consolidate_schedules, generate_lease_schedule, pv_of_lease_payments
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
