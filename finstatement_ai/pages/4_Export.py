"""Page 4 — Export the assembled financial statement package."""

from __future__ import annotations

import re

import streamlit as st

from utils.checklist import REQUIRED, NA, progress
from utils.pdf_builder import build_pdf, build_session_excel


st.set_page_config(page_title="Export — FinStatement AI", layout="wide")


def _require_api_key():
    if not st.session_state.get("api_key_validated"):
        st.warning("Please enter and validate your Anthropic API key on the home page first.")
        st.stop()


def _safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", text or "")
    return cleaned.strip("_") or "Entity"


def _render_checklist_review():
    st.subheader("GAAP Disclosure Checklist — pre-export review")
    checklist = st.session_state.checklist or []
    if not checklist:
        st.info("No checklist generated yet. Visit Statements or Notes first.")
        return False

    completed, total = progress(checklist)
    st.progress(
        (completed / total) if total else 1.0,
        text=f"{completed} of {total} required disclosures complete",
    )

    incomplete_required = [
        c for c in checklist
        if c.get("status") == REQUIRED and not c.get("complete")
    ]
    if incomplete_required:
        st.error(
            f"⚠ {len(incomplete_required)} required disclosure(s) are not marked complete. "
            f"You may proceed anyway by acknowledging below."
        )
        for c in incomplete_required:
            st.markdown(f"- **{c.get('title')}** ({c.get('category')})")
        ack = st.checkbox(
            "I acknowledge that required disclosures are incomplete and want to export anyway.",
            key="ack_incomplete",
        )
        return ack
    st.success("All required disclosures are marked complete.")
    return True


def _render_export_buttons():
    st.subheader("Download")
    entity_name = st.session_state.entity_name or "Entity"
    fye_str = str(st.session_state.fiscal_year_end or "FYE")
    safe_entity = _safe_filename(entity_name)
    safe_fye = _safe_filename(fye_str)

    include_checklist = st.checkbox("Include GAAP Disclosure Checklist appendix in PDF", value=False)

    cols = st.columns(2)
    with cols[0]:
        if st.button("Generate PDF", type="primary"):
            with st.spinner("Building PDF..."):
                try:
                    pdf_bytes = build_pdf(
                        entity_name=entity_name,
                        entity_type=st.session_state.entity_type,
                        fiscal_year_end=fye_str,
                        statements=st.session_state.statements or {},
                        notes=st.session_state.notes or [],
                        checklist=st.session_state.checklist or [],
                        include_checklist_appendix=include_checklist,
                    )
                except Exception as e:
                    st.error(f"PDF build failed: {e}")
                    return
            st.session_state["_pdf_bytes"] = pdf_bytes
            st.success("PDF ready.")

        if "_pdf_bytes" in st.session_state and st.session_state["_pdf_bytes"]:
            st.download_button(
                "📄 Download Financial Statements PDF",
                data=st.session_state["_pdf_bytes"],
                file_name=f"{safe_entity}_FinancialStatements_{safe_fye}.pdf",
                mime="application/pdf",
            )

    with cols[1]:
        if st.button("Generate session workbook"):
            with st.spinner("Building Excel workbook..."):
                try:
                    xlsx_bytes = build_session_excel(
                        parsed_tb=st.session_state.parsed_tb,
                        statements=st.session_state.statements or {},
                        notes=st.session_state.notes or [],
                    )
                except Exception as e:
                    st.error(f"Workbook build failed: {e}")
                    return
            st.session_state["_xlsx_bytes"] = xlsx_bytes
            st.success("Workbook ready.")

        if "_xlsx_bytes" in st.session_state and st.session_state["_xlsx_bytes"]:
            st.download_button(
                "📊 Download session workbook (re-uploadable)",
                data=st.session_state["_xlsx_bytes"],
                file_name=f"{safe_entity}_SessionData_{safe_fye}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )


def main():
    _require_api_key()
    st.title("Export")
    st.caption(
        "Final review before generating the deliverable. The PDF assembles cover page, "
        "statements, notes, and an optional checklist appendix."
    )

    if not st.session_state.statements:
        st.warning("Build your statements before exporting.")
        st.stop()

    can_proceed = _render_checklist_review()
    st.divider()

    if not can_proceed:
        st.warning("Acknowledge the incomplete disclosures above to enable export downloads.")
        return

    _render_export_buttons()


main()
