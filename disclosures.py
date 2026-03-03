from __future__ import annotations

from datetime import date

import pandas as pd


def build_disclosure_table(schedules: pd.DataFrame, fiscal_year_end: date) -> pd.DataFrame:
    year = fiscal_year_end.year
    year_sched = schedules[pd.to_datetime(schedules["date"]).dt.year == year].copy()
    fin = year_sched[year_sched["classification"] == "finance"]
    op = year_sched[year_sched["classification"] == "operating"]

    finance_amort = fin["rou_amortization"].sum()
    finance_interest = fin["interest_expense"].sum()
    operating_expense = op["lease_expense"].sum()
    variable_expense = year_sched["variable_payment"].sum()

    data = [
        ("Lease expense", ""),
        ("Finance lease expense", ""),
        ("Amortization of ROU assets", finance_amort),
        ("Interest on lease liabilities", finance_interest),
        ("Operating lease expense", operating_expense),
        ("Short-term lease expense *", 0.0),
        ("Variable lease expense", variable_expense),
        ("Sublease income *", 0.0),
        ("Total", finance_amort + finance_interest + operating_expense + variable_expense),
        ("Other Information", ""),
        ("(Gains) losses on sale-leaseback transactions, net *", 0.0),
        ("Cash paid for amounts included in the measurement of lease liabilities", ""),
        ("Operating cash flows from finance leases (i.e. Interest)", finance_interest),
        ("Financing cash flows from finance leases (i.e. principal portion)", fin["principal"].sum()),
        ("Operating cash flows from operating leases", op["payment"].sum()),
        ("ROU assets obtained in exchange for new finance lease liabilities", 0.0),
        ("ROU assets obtained in exchange for new operating  lease liabilities", 0.0),
        ("Weighted-average remaining lease term in years for finance leases", _weighted_avg_remaining_years(fin, fiscal_year_end)),
        ("Weighted-average remaining lease term in years for operating leases", _weighted_avg_remaining_years(op, fiscal_year_end)),
        ("Weighted-average discount rate for finance leases", _weighted_avg_rate(fin)),
        ("Weighted-average discount rate for operating leases", _weighted_avg_rate(op)),
    ]

    return pd.DataFrame(data, columns=["Label", "Amount"])


def maturity_analysis(schedules: pd.DataFrame, fiscal_year_end: date) -> pd.DataFrame:
    future = schedules[pd.to_datetime(schedules["date"]) > pd.Timestamp(fiscal_year_end)]
    rows = []
    for i in range(1, 6):
        yr = fiscal_year_end.year + i
        label = f"{yr}-12"
        yr_data = future[pd.to_datetime(future["date"]).dt.year == yr]
        rows.append((label, yr_data[yr_data["classification"] == "finance"]["payment"].sum(), yr_data[yr_data["classification"] == "operating"]["payment"].sum()))

    remaining = future[pd.to_datetime(future["date"]).dt.year > fiscal_year_end.year + 5]
    rows.append(("Thereafter", remaining[remaining["classification"] == "finance"]["payment"].sum(), remaining[remaining["classification"] == "operating"]["payment"].sum()))

    m = pd.DataFrame(rows, columns=["Label", "Finance", "Operating"])
    total_fin = m["Finance"].sum()
    total_op = m["Operating"].sum()

    fin_disc = total_fin - future[future["classification"] == "finance"]["end_liability"].tail(1).sum()
    op_disc = total_op - future[future["classification"] == "operating"]["end_liability"].tail(1).sum()

    m = pd.concat(
        [
            m,
            pd.DataFrame(
                [
                    ("Total undiscounted cash flows", total_fin, total_op),
                    ("Less:  present value discount", fin_disc, op_disc),
                    ("Total lease liabilities", total_fin - fin_disc, total_op - op_disc),
                ],
                columns=["Label", "Finance", "Operating"],
            ),
        ],
        ignore_index=True,
    )
    return m


def _weighted_avg_rate(df: pd.DataFrame) -> float:
    if df.empty:
        return 0.0
    rates = df.groupby("lease_id").first().get("interest_expense", pd.Series(dtype=float))
    payments = df.groupby("lease_id")["payment"].sum()
    if payments.sum() == 0:
        return 0.0
    return float((rates * payments).sum() / payments.sum())


def _weighted_avg_remaining_years(df: pd.DataFrame, fiscal_year_end: date) -> float:
    if df.empty:
        return 0.0
    d = df[pd.to_datetime(df["date"]) > pd.Timestamp(fiscal_year_end)]
    if d.empty:
        return 0.0
    rem_months = d.groupby("lease_id").size()
    return float((rem_months / 12).mean())
