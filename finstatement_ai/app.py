"""FinStatement AI — Streamlit entry point.

Handles:
- API key gate (validated via a lightweight Claude call)
- Session-state initialization
- Sidebar navigation and Reset Session control
"""

from __future__ import annotations

import streamlit as st

from utils.ai_engine import validate_api_key


st.set_page_config(
    page_title="FinStatement AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


def init_session_state() -> None:
    defaults = {
        "api_key": "",
        "api_key_validated": False,
        "entity_type": "For-Profit",
        "basis": "Accrual",
        "entity_name": "",
        "fiscal_year_end": None,
        "statements_selected": [],
        "cash_flow_method": "Indirect",
        "uploaded_source_type": "",
        "raw_uploaded_filename": "",
        "parsed_tb": None,            # standardized DataFrame
        "py_notes_text": "",          # text blob from prior year notes (if uploaded)
        "statements": {},             # dict: statement_name -> list of rows
        "checklist": [],              # list of checklist items
        "notes": [],                  # list of note dicts
        "facts": {                    # flags driving the checklist engine
            "has_leases": False,
            "has_income_taxes": False,
            "has_stock_comp": False,
            "has_benefit_plans": False,
        },
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_session() -> None:
    keys_to_clear = list(st.session_state.keys())
    for k in keys_to_clear:
        del st.session_state[k]
    init_session_state()


def render_api_key_gate() -> bool:
    """Sidebar API key entry. Returns True once the key is validated."""
    st.sidebar.header("Anthropic API key")
    if st.session_state.api_key_validated:
        st.sidebar.success("API key validated")
        if st.sidebar.button("Change API key"):
            st.session_state.api_key = ""
            st.session_state.api_key_validated = False
            st.rerun()
        return True

    key_input = st.sidebar.text_input(
        "Enter your Anthropic API key",
        type="password",
        value=st.session_state.api_key,
        help="Get a key at https://console.anthropic.com. The key is held in session state and never written to disk.",
    )
    if st.sidebar.button("Validate key", type="primary", disabled=not key_input):
        with st.spinner("Validating API key..."):
            ok, msg = validate_api_key(key_input)
        if ok:
            st.session_state.api_key = key_input.strip()
            st.session_state.api_key_validated = True
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)
    return False


def render_sidebar_controls() -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Session")
    if st.sidebar.button("Reset Session", help="Clear all uploaded data, statements, and notes."):
        reset_session()
        st.rerun()
    st.sidebar.caption(f"Entity: {st.session_state.entity_name or '(not set)'}")
    st.sidebar.caption(f"Type: {st.session_state.entity_type}")


def main() -> None:
    init_session_state()

    st.title("FinStatement AI")
    st.caption("AI-assisted preparation of GAAP-compliant financial statements (FASB and ASC 958)")

    if not render_api_key_gate():
        st.info(
            "Enter your Anthropic API key in the sidebar to begin. "
            "Once validated, use the navigation in the left sidebar to move through Upload → Statements → Notes → Export."
        )
        st.stop()

    render_sidebar_controls()

    st.markdown(
        """
### Workflow

1. **Upload** — set entity details and upload either a prior-year financial statement or a current-year trial balance.
2. **Statements** — review, edit, and balance the financial statements selected for this engagement.
3. **Notes** — review AI-drafted notes; redo, expand, or apply custom edits as needed.
4. **Export** — download the assembled PDF and a re-uploadable session workbook.

Use the **Reset Session** button in the sidebar to clear all data and start over.
"""
    )


if __name__ == "__main__":
    main()
else:
    main()
