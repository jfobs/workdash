from __future__ import annotations

from datetime import date
from io import BytesIO

import pandas as pd
import streamlit as st

from ai.narratives import draft_narrative
from ai.pdf_ingest import extract_leases_from_pdf
from disclosures import build_disclosure_table
from exports.docx_export import create_note_docx
from exports.excel_export import create_audit_workbook
from lease_engine import consolidate_schedules, generate_lease_schedule
from models import LeaseInput

st.set_page_config(page_title="LeaseWorkbench", layout="wide")
st.title("📋 ASC 842 Lease Manager")

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
    "escalation_rate_annual",
    "escalation_interval_months",
    "rent_steps_json",
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
                "lease_name": "2932 Lime Street",
                "classification": "operating",
                "commencement_date": "2025-02-27",
                "payment_frequency": "monthly",
                "payment_amount": 2500,
                "payment_timing": "BOM",
                "lease_term_months": 60,
                "annual_discount_rate": 0.05,
                "escalation_rate_annual": 0.03,
                "escalation_interval_months": 12,
                "rent_steps_json": '{"1":2500,"13":2575,"25":2652.25}',
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

st.sidebar.header("Import / Export")
uploaded = st.sidebar.file_uploader("Upload portfolio (Excel/CSV)", type=["xlsx", "csv"])
pdf_uploads = st.sidebar.file_uploader("Upload lease contracts (PDF)", type=["pdf"], accept_multiple_files=True)
extract_pdf = st.sidebar.button("Extract leases from PDFs")
fy_end = st.sidebar.date_input("Fiscal year end", value=date(2024, 12, 31))
use_comp = st.sidebar.checkbox("Include comparative year", value=False)
comp_end = st.sidebar.date_input("Comparative year end", value=date(2023, 12, 31), disabled=not use_comp)
class_filter = st.sidebar.selectbox("Classification filter", ["all", "operating", "finance"])

st.sidebar.header("AI Settings")
ai_toggle = st.sidebar.toggle("AI narrative", value=False)
openai_api_key = st.sidebar.text_input("OpenAI API Key", type="password", help="Optional: overrides OPENAI_API_KEY env var for this session.")
ai_model = st.sidebar.selectbox("OpenAI model", ["gpt-5.2", "gpt-5.2-mini", "gpt-4.1"], index=0)

st.sidebar.download_button("Download template", data=template_bytes(), file_name="lease_template.xlsx")

if uploaded:
    st.session_state.portfolio = pd.read_csv(uploaded) if uploaded.name.endswith(".csv") else pd.read_excel(uploaded)

if extract_pdf and pdf_uploads:
    extracted_rows, extraction_errors = [], []
    for file in pdf_uploads:
        try:
            leases = extract_leases_from_pdf(file.getvalue(), model=ai_model, api_key=openai_api_key or None, filename=file.name)
            if not leases:
                extraction_errors.append(f"{file.name}: no lease terms detected after text+OCR+transcription parsing (try gpt-5.2 model or enter core terms manually)")
            extracted_rows.extend(leases)
        except Exception as exc:
            extraction_errors.append(f"{file.name}: {exc}")
    if extracted_rows:
        st.session_state.portfolio = pd.concat([st.session_state.portfolio, pd.DataFrame(extracted_rows)], ignore_index=True)
        st.sidebar.success(f"Extracted {len(extracted_rows)} lease row(s)")
    if extraction_errors:
        st.sidebar.warning("\n".join(extraction_errors))

portfolio = st.session_state.portfolio.copy()
if not portfolio.empty and class_filter != "all":
    portfolio = portfolio[portfolio["classification"] == class_filter]

schedules = []
for _, row in portfolio.iterrows():
    try:
        schedules.append(generate_lease_schedule(LeaseInput(**row.to_dict())))
    except Exception:
        continue
all_sched = pd.concat(schedules, ignore_index=True) if schedules else pd.DataFrame()

# Top nav like requested screenshot style
portfolio_tab, lease_detail_tab, journal_tab, disclosures_tab, io_tab = st.tabs(
    ["📊 Dashboard", "📁 Lease Detail", "🧾 Journal Entries", "📄 Disclosures", "📥 Import / Export"]
)

with portfolio_tab:
    st.subheader("Portfolio")
    edited = st.data_editor(st.session_state.portfolio, num_rows="dynamic", use_container_width=True)
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

with lease_detail_tab:
    st.subheader("Lease Detail")
    if portfolio.empty:
        st.info("Load portfolio first.")
    else:
        lease_id = st.selectbox("Select Lease", portfolio["lease_id"].astype(str).tolist())
        src = portfolio[portfolio["lease_id"].astype(str) == lease_id].iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Type", str(src.get("classification", "")).title())
        c2.metric("Start", str(src.get("commencement_date", "")))
        c3.metric("Rate", f"{float(src.get('annual_discount_rate', 0))*100:.2f}%")
        c4.metric("Timing", str(src.get("payment_timing", "")))
        st.caption("Rent step inputs: use annual escalation fields or JSON steps like {'1':2500,'13':2575}.")

        df = all_sched[all_sched["lease_id"].astype(str) == lease_id]
        st.dataframe(df, use_container_width=True)
        bio = BytesIO()
        df.to_excel(bio, index=False)
        st.download_button("Download lease schedule", bio.getvalue(), file_name=f"{lease_id}_schedule.xlsx")

with journal_tab:
    st.subheader("Journal Entries")
    if all_sched.empty:
        st.info("No schedules available.")
    else:
        je = all_sched[["date", "lease_id", "lease_expense", "interest_expense", "principal", "payment"]].copy()
        je.columns = ["Date", "Lease", "Expense", "Interest", "Principal", "Cash/AP"]
        st.dataframe(je, use_container_width=True)

with disclosures_tab:
    st.subheader("ASC 842 Disclosure")
    if all_sched.empty:
        st.info("No schedules available.")
    else:
        st.dataframe(build_disclosure_table(all_sched, fy_end), use_container_width=True)

with io_tab:
    st.subheader("Import / Export")
    st.write("Use sidebar for imports. Generate exports below.")
    st.dataframe(consolidate_schedules(schedules), use_container_width=True)

    default_lines = [
        "EK obtained all leases for testing and reconciled to source data.",
        "Results: Lease calculations agree to independent recomputation within tolerance.",
        "Conclusion: No material exceptions noted.",
    ]
    lines_text = st.text_area("Data sheet narrative lines", "\n".join(default_lines), height=120)
    user_narrative = st.text_area("Note narrative text", "Leasing activities are presented below.")

    if st.button("Draft narrative with AI"):
        suggestion = draft_narrative({"fiscal_year": str(fy_end), "lease_count": len(portfolio)}, enabled=ai_toggle, model=ai_model, api_key=openai_api_key or None)
        st.write(suggestion)

    if st.button("Generate Audit Workbook") and not all_sched.empty:
        data = create_audit_workbook(all_sched, fy_end, lines_text.splitlines())
        st.download_button("Download audit workbook", data=data, file_name=f"lease_audit_{fy_end.year}.xlsx")

    if st.button("Generate Note DOCX") and not all_sched.empty:
        comparative_sched = None
        if use_comp:
            comparative_sched = all_sched[pd.to_datetime(all_sched["date"]).dt.year == comp_end.year].copy()
        doc = create_note_docx(all_sched, fy_end, narrative=user_narrative, comparative_schedules=comparative_sched)
        st.download_button("Download note docx", data=doc, file_name=f"lease_note_{fy_end.year}.docx")
