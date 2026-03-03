from __future__ import annotations

import json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, getcontext

import pandas as pd

from models import EngineSettings, LeaseInput

getcontext().prec = 28


def quantize(value: Decimal, places: int = 2) -> Decimal:
    q = Decimal("1").scaleb(-places)
    return value.quantize(q, rounding=ROUND_HALF_UP)


def add_months(start: date, months: int) -> date:
    return (pd.Timestamp(start) + pd.offsets.MonthEnd(months)).date()


def pv_of_lease_payments(payment_amount: Decimal, periodic_rate: Decimal, n_periods: int, payment_timing: str) -> Decimal:
    if periodic_rate == 0:
        pv = payment_amount * n_periods
    else:
        factor = (Decimal("1") - (Decimal("1") + periodic_rate) ** (-n_periods)) / periodic_rate
        pv = payment_amount * factor
        if payment_timing == "BOM":
            pv *= (Decimal("1") + periodic_rate)
    return pv


def pv_of_payment_stream(payments: list[Decimal], periodic_rate: Decimal, payment_timing: str) -> Decimal:
    pv = Decimal("0")
    for i, pmt in enumerate(payments, start=1):
        exp = i if payment_timing == "EOM" else i - 1
        if periodic_rate == 0:
            pv += pmt
        else:
            pv += pmt / ((Decimal("1") + periodic_rate) ** exp)
    return pv


def build_payment_stream(lease: LeaseInput) -> list[Decimal]:
    n = int(lease.lease_term_months or 0)
    base = lease.payment_amount
    steps: dict[int, Decimal] = {}

    if lease.rent_steps_json:
        try:
            raw = json.loads(lease.rent_steps_json)
            if isinstance(raw, dict):
                steps = {int(k): Decimal(str(v)) for k, v in raw.items()}
            elif isinstance(raw, list):
                steps = {int(item["period"]): Decimal(str(item["amount"])) for item in raw}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            steps = {}

    payments: list[Decimal] = []
    current = base
    for period in range(1, n + 1):
        if period in steps:
            current = steps[period]
        elif period > 1 and lease.escalation_rate_annual and (period - 1) % lease.escalation_interval_months == 0:
            current = current * (Decimal("1") + lease.escalation_rate_annual)
        payments.append(current)
    return payments


def generate_lease_schedule(lease: LeaseInput, settings: EngineSettings | None = None) -> pd.DataFrame:
    settings = settings or EngineSettings()
    n = int(lease.lease_term_months or 0)
    r = lease.annual_discount_rate / Decimal("12")

    payment_stream = build_payment_stream(lease)
    liability_0 = pv_of_payment_stream(payment_stream, r, lease.payment_timing)
    rou_0 = liability_0 + lease.initial_direct_costs + lease.prepaid_rent - lease.lease_incentives

    total_fixed = sum(payment_stream)
    straight_line_cost = (total_fixed - lease.lease_incentives) / n if n else Decimal("0")
    rou_straight_amort = rou_0 / n if n else Decimal("0")

    rows = []
    liability = liability_0
    rou = rou_0

    for period in range(1, n + 1):
        period_end = add_months(lease.commencement_date, period - 1)
        begin_liability = liability
        begin_rou = rou
        payment = payment_stream[period - 1]

        payment_bom = Decimal("0")
        payment_eom = Decimal("0")

        if lease.payment_timing == "BOM":
            payment_bom = min(payment, begin_liability)
            base_for_interest = begin_liability - payment_bom
            interest = base_for_interest * r
            end_liability = base_for_interest + interest
            principal = payment_bom - interest
        else:
            interest = begin_liability * r
            payment_eom = min(payment, begin_liability + interest)
            principal = payment_eom - interest
            end_liability = begin_liability + interest - payment_eom

        if lease.classification == "finance":
            rou_amort = rou_straight_amort
            lease_expense = rou_amort + interest
        else:
            lease_expense = straight_line_cost
            rou_amort = lease_expense - interest

        end_rou = begin_rou - rou_amort

        if period == n:
            if abs(end_liability) <= settings.true_up_tolerance:
                end_liability = Decimal("0")
            if abs(end_rou) <= settings.true_up_tolerance:
                end_rou = Decimal("0")

        st_liability = principal if principal > 0 else Decimal("0")
        lt_liability = end_liability - st_liability

        rows.append(
            {
                "lease_id": lease.lease_id,
                "lease_name": lease.lease_name,
                "classification": lease.classification,
                "period": period,
                "date": period_end,
                "month": period_end.strftime("%Y-%m"),
                "payment": payment,
                "payment_bom": payment_bom,
                "payment_eom": payment_eom,
                "begin_liability": begin_liability,
                "interest_expense": interest,
                "principal": principal,
                "end_liability": end_liability,
                "rou_begin": begin_rou,
                "rou_amortization": rou_amort,
                "rou_end": end_rou,
                "lease_expense": lease_expense,
                "variable_payment": lease.variable_payment_amount,
                "nonlease_payment": lease.nonlease_component_payment,
                "st_liability": st_liability,
                "lt_liability": lt_liability,
                "annual_discount_rate": lease.annual_discount_rate,
            }
        )

        liability = end_liability
        rou = end_rou

    df = pd.DataFrame(rows)
    for c in [
        "payment",
        "payment_bom",
        "payment_eom",
        "begin_liability",
        "interest_expense",
        "principal",
        "end_liability",
        "rou_begin",
        "rou_amortization",
        "rou_end",
        "lease_expense",
        "variable_payment",
        "nonlease_payment",
        "st_liability",
        "lt_liability",
    ]:
        df[c] = df[c].map(lambda x: float(quantize(Decimal(x), settings.currency_rounding)))
    df["annual_discount_rate"] = df["annual_discount_rate"].astype(float)
    return df


def consolidate_schedules(schedules: list[pd.DataFrame]) -> pd.DataFrame:
    if not schedules:
        return pd.DataFrame()
    full = pd.concat(schedules, ignore_index=True)
    grouped = (
        full.groupby(["month", "classification"], as_index=False)[
            ["payment", "interest_expense", "principal", "end_liability", "rou_end", "lease_expense"]
        ]
        .sum()
        .sort_values(["month", "classification"])
    )
    return grouped


def liability_split_next_12_months(schedule: pd.DataFrame, as_of: date) -> tuple[float, float]:
    if schedule.empty:
        return 0.0, 0.0
    future = schedule[schedule["date"] > as_of]
    future_12 = future[future["date"] <= (pd.Timestamp(as_of) + pd.DateOffset(months=12)).date()]
    st = future_12["principal"].sum()
    total = future["end_liability"].iloc[0] if not future.empty else 0.0
    lt = max(total - st, 0.0)
    return float(st), float(lt)
