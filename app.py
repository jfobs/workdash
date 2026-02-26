from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from ai.narratives import draft_narrative
from disclosures import build_disclosure_table
from exports.docx_export import create_note_docx
from exports.excel_export import create_audit_workbook
from lease_engine import consolidate_schedules, generate_lease_schedule
from models import LeaseInput

st.set_page_config(page_title="LeaseWorkbench", layout="wide")
st.title("LeaseWorkbench")

TEMPLATE_COLUMNS = [
    "lease_id",
    "lease_name",
    "classification",
    "commencement_date",
    "payment_frequency",
    "payment_amount",
    "payment_timing",
    "lease_term_months",
    "annual_discount_rate",
    "lease_incentives",
    "initial_direct_costs",
    "prepaid_rent",
    "residual_value_guarantee",
    "variable_payment_amount",
    "nonlease_component_payment",
]


@st.cache_data
def template_bytes() -> bytes:
    df = pd.DataFrame(
        [
            {
                "lease_id": "L-001",
                "lease_name": "HQ Office",
                "classification": "operating",
                "commencement_date": "2024-01-01",
                "payment_frequency": "monthly",
                "payment_amount": 10000,
                "payment_timing": "EOM",
                "lease_term_months": 36,
                "annual_discount_rate": 0.05,
                "lease_incentives": 0,
                "initial_direct_costs": 0,
                "prepaid_rent": 0,
                "residual_value_guarantee": 0,
                "variable_payment_amount": 0,
                "nonlease_component_payment": 0,
            }
        ]
    )
    bio = BytesIO()
    df.to_excel(bio, index=False)
    return bio.getvalue()


if "portfolio" not in st.session_state:
    st.session_state.portfolio = pd.DataFrame(columns=TEMPLATE_COLUMNS)

st.sidebar.header("Inputs")
uploaded = st.sidebar.file_uploader("Upload portfolio (Excel/CSV)", type=["xlsx", "csv"])
fy_end = st.sidebar.date_input("Fiscal year end", value=date(2024, 12, 31))
comp_end = st.sidebar.date_input("Comparative year end (optional)", value=None)
class_filter = st.sidebar.selectbox("Classification filter", ["all", "operating", "finance"])
ai_toggle = st.sidebar.toggle("AI narrative", value=False)

st.sidebar.download_button("Download template", data=template_bytes(), file_name="lease_template.xlsx")

if uploaded:
    if uploaded.name.endswith(".csv"):
        st.session_state.portfolio = pd.read_csv(uploaded)
    else:
        st.session_state.portfolio = pd.read_excel(uploaded)

page = st.sidebar.radio(
    "Page",
    ["Portfolio", "Lease Detail", "Consolidation", "Disclosures", "Exports", "Settings"],
)

if page == "Portfolio":
    st.subheader("Portfolio")
    edited = st.data_editor(st.session_state.portfolio, num_rows="dynamic")
    st.session_state.portfolio = edited
    warnings = []
    for _, row in edited.iterrows():
        try:
            LeaseInput(**row.to_dict())
        except Exception as exc:
            warnings.append(f"{row.get('lease_id', 'Unknown')}: {exc}")
    if warnings:
        st.warning("\n".join(warnings))
    else:
        st.success("All lease rows are valid.")

portfolio = st.session_state.portfolio.copy()
if not portfolio.empty and class_filter != "all":
    portfolio = portfolio[portfolio["classification"] == class_filter]

schedules = []
for _, row in portfolio.iterrows():
    try:
        lease = LeaseInput(**row.to_dict())
        schedules.append(generate_lease_schedule(lease))
    except Exception:
        continue

all_sched = pd.concat(schedules, ignore_index=True) if schedules else pd.DataFrame()

if page == "Lease Detail":
    st.subheader("Lease Detail")
    if portfolio.empty:
        st.info("Load portfolio first.")
    else:
        lease_id = st.selectbox("Select Lease", portfolio["lease_id"].astype(str).tolist())
        df = all_sched[all_sched["lease_id"].astype(str) == lease_id]
        st.dataframe(df, use_container_width=True)
        bio = BytesIO()
        df.to_excel(bio, index=False)
        st.download_button("Download lease schedule", bio.getvalue(), file_name=f"{lease_id}_schedule.xlsx")

if page == "Consolidation":
    st.subheader("Consolidated monthly totals")
    st.dataframe(consolidate_schedules(schedules), use_container_width=True)

if page == "Disclosures":
    st.subheader("ASC 842 disclosure table")
    if all_sched.empty:
        st.info("No schedules available.")
    else:
        st.dataframe(build_disclosure_table(all_sched, fy_end), use_container_width=True)

if page == "Exports":
    st.subheader("Exports")
    default_lines = [
        "EK obtained all leases for testing and reconciled to source data.",
        "Results: Lease calculations agree to independent recomputation within tolerance.",
        "Conclusion: No material exceptions noted.",
    ]
    lines_text = st.text_area("Data sheet narrative lines (one per line)", "\n".join(default_lines), height=140)
    user_narrative = st.text_area("Note narrative text", "Leasing activities are presented below.")

    if st.button("Draft narrative with AI"):
        suggestion = draft_narrative({"fiscal_year": str(fy_end), "lease_count": len(portfolio)}, enabled=ai_toggle)
        st.write(suggestion)

    if st.button("Generate Audit Workbook") and not all_sched.empty:
        data = create_audit_workbook(all_sched, fy_end, lines_text.splitlines())
        st.download_button("Download audit workbook", data=data, file_name=f"lease_audit_{fy_end.year}.xlsx")

    if st.button("Generate Note DOCX") and not all_sched.empty:
        doc = create_note_docx(all_sched, fy_end, narrative=user_narrative)
        st.download_button("Download note docx", data=doc, file_name=f"lease_note_{fy_end.year}.docx")

if page == "Settings":
    st.subheader("Settings")
    st.markdown("- Sign conventions toggle currently handled in exports roadmap (TODO).")
    st.markdown("- Rounding is fixed at 2 decimals for display; high precision internal calculations.")
