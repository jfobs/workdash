"""Page 1 — Entity setup and source data upload."""

from __future__ import annotations

from datetime import date

import streamlit as st

from utils import parser
from utils.ai_engine import suggest_account_mapping
from utils.mappings import (
    ENTITY_FOR_PROFIT,
    ENTITY_NONPROFIT,
    STATEMENT_BALANCE_SHEET,
    STATEMENT_INCOME,
    STATEMENT_CASH_FLOW,
    STATEMENT_EQUITY,
    STATEMENT_ACTIVITIES,
    STATEMENT_FINANCIAL_POSITION,
    STATEMENT_FUNCTIONAL_EXPENSES,
)


st.set_page_config(page_title="Upload — FinStatement AI", layout="wide")


def _require_api_key():
    if not st.session_state.get("api_key_validated"):
        st.warning("Please enter and validate your Anthropic API key on the home page first.")
        st.stop()


def render_entity_setup() -> None:
    st.subheader("Entity setup")
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.entity_type = st.selectbox(
            "Entity Type",
            [ENTITY_FOR_PROFIT, ENTITY_NONPROFIT],
            index=[ENTITY_FOR_PROFIT, ENTITY_NONPROFIT].index(st.session_state.entity_type),
        )
        st.session_state.basis = st.selectbox(
            "Basis of Presentation",
            ["Accrual", "Cash"],
            index=["Accrual", "Cash"].index(st.session_state.basis),
        )
        st.session_state.entity_name = st.text_input(
            "Entity Name",
            value=st.session_state.entity_name,
            placeholder="e.g., Acme, Inc.",
        )
    with col2:
        default_fye = st.session_state.fiscal_year_end or date(date.today().year - 1, 12, 31)
        st.session_state.fiscal_year_end = st.date_input(
            "Fiscal Year End",
            value=default_fye,
        )

    is_nonprofit = st.session_state.entity_type == ENTITY_NONPROFIT

    if is_nonprofit:
        all_options = [
            STATEMENT_FINANCIAL_POSITION,
            STATEMENT_ACTIVITIES,
            STATEMENT_CASH_FLOW,
            STATEMENT_FUNCTIONAL_EXPENSES,
        ]
        default = [STATEMENT_FINANCIAL_POSITION, STATEMENT_ACTIVITIES, STATEMENT_CASH_FLOW, STATEMENT_FUNCTIONAL_EXPENSES]
    else:
        all_options = [
            STATEMENT_BALANCE_SHEET,
            STATEMENT_INCOME,
            STATEMENT_CASH_FLOW,
            STATEMENT_EQUITY,
        ]
        default = [STATEMENT_BALANCE_SHEET, STATEMENT_INCOME, STATEMENT_CASH_FLOW]

    selected = st.session_state.statements_selected or default
    selected = [s for s in selected if s in all_options]
    st.session_state.statements_selected = st.multiselect(
        "Statements to Prepare",
        options=all_options,
        default=selected,
    )

    if STATEMENT_CASH_FLOW in st.session_state.statements_selected:
        st.session_state.cash_flow_method = st.radio(
            "Cash Flow Method",
            ["Indirect", "Direct"],
            index=["Indirect", "Direct"].index(st.session_state.cash_flow_method),
            horizontal=True,
        )

    st.divider()
    st.markdown("**Engagement-specific flags** (these drive the GAAP disclosure checklist):")
    fcols = st.columns(4)
    with fcols[0]:
        st.session_state.facts["has_leases"] = st.checkbox(
            "Has leases (ASC 842)", value=st.session_state.facts.get("has_leases", False)
        )
    with fcols[1]:
        st.session_state.facts["has_income_taxes"] = st.checkbox(
            "Has income tax provision", value=st.session_state.facts.get("has_income_taxes", False)
        )
    with fcols[2]:
        st.session_state.facts["has_stock_comp"] = st.checkbox(
            "Has stock-based compensation", value=st.session_state.facts.get("has_stock_comp", False)
        )
    with fcols[3]:
        st.session_state.facts["has_benefit_plans"] = st.checkbox(
            "Has employee benefit plans", value=st.session_state.facts.get("has_benefit_plans", False)
        )


def render_upload() -> None:
    st.subheader("Upload source data")
    source_type = st.radio(
        "Source type",
        [
            "Trial Balance / Grouping Report",
            "Prior Year Financial Statement",
        ],
        index=0 if st.session_state.uploaded_source_type != "prior_year_fs" else 1,
        help="Trial balance: raw account balances. Prior year FS: structured output from a prior year FinStatement AI run.",
    )

    uploaded = st.file_uploader(
        "Upload Excel or CSV",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=False,
    )

    if uploaded is None:
        return

    sheet_name = None
    sheets = parser.list_excel_sheets(uploaded)
    if sheets:
        sheet_name = st.selectbox("Sheet", sheets)

    if not st.button("Parse upload", type="primary"):
        return

    with st.spinner("Parsing uploaded file..."):
        try:
            if source_type == "Prior Year Financial Statement":
                df = parser.parse_prior_year_fs(uploaded, sheet_name=sheet_name)
                st.session_state.uploaded_source_type = "prior_year_fs"
            else:
                df = parser.parse_trial_balance(uploaded, sheet_name=sheet_name)
                st.session_state.uploaded_source_type = "trial_balance"
        except Exception as e:
            st.error(f"Could not parse the upload: {e}")
            return

    if df is None or df.empty:
        st.error("The upload was parsed but no rows were detected. Check the file structure.")
        return

    st.session_state.raw_uploaded_filename = uploaded.name

    if not parser.has_grouping(df) and st.session_state.uploaded_source_type == "trial_balance":
        st.info("No grouping/classification column detected — asking Claude to suggest GAAP line-item mappings.")
        try:
            with st.spinner("Generating account mappings (Claude)..."):
                df = suggest_account_mapping(
                    api_key=st.session_state.api_key,
                    accounts_df=df,
                    entity_type=st.session_state.entity_type,
                )
        except Exception as e:
            st.error(f"AI mapping failed; falling back to keyword heuristics. ({e})")
        df = parser.fallback_mapping(df)

    st.session_state.parsed_tb = df
    st.success(f"Parsed {len(df)} rows from {uploaded.name}.")


def render_data_preview() -> None:
    df = st.session_state.parsed_tb
    if df is None or df.empty:
        return
    st.subheader("Data preview & corrections")
    st.caption("Edit any row to fix mapping errors before proceeding to the Statements page.")
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        key="tb_editor",
        column_config={
            "py_balance": st.column_config.NumberColumn("Prior Year", format="$%.2f"),
            "cy_balance": st.column_config.NumberColumn("Current Year", format="$%.2f"),
            "debit": st.column_config.NumberColumn("Debit", format="$%.2f"),
            "credit": st.column_config.NumberColumn("Credit", format="$%.2f"),
        },
    )
    if st.button("Save edits"):
        st.session_state.parsed_tb = edited
        st.success("Edits saved.")


def main() -> None:
    _require_api_key()
    st.title("Upload")
    render_entity_setup()
    st.divider()
    render_upload()
    render_data_preview()
    if st.session_state.parsed_tb is not None and not st.session_state.parsed_tb.empty:
        st.info("Continue to the **Statements** page in the left sidebar.")


main()
