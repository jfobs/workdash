"""FinStatement AI — Streamlit entry point.

Handles:
- Provider + API key gate (Anthropic Claude or OpenAI GPT, validated via a
  lightweight call)
- Session-state initialization
- Sidebar navigation and Reset Session control
"""

from __future__ import annotations

import streamlit as st

from utils.ai_engine import (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    validate_api_key,
)


st.set_page_config(
    page_title="FinStatement AI",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


PROVIDER_LABELS = {
    PROVIDER_ANTHROPIC: "Anthropic (Claude)",
    PROVIDER_OPENAI: "OpenAI (GPT)",
}
PROVIDER_HELP = {
    PROVIDER_ANTHROPIC: "Get a key at https://console.anthropic.com",
    PROVIDER_OPENAI: "Get a key at https://platform.openai.com/api-keys",
}


def init_session_state() -> None:
    defaults = {
        "provider": PROVIDER_ANTHROPIC,
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
        "parsed_tb": None,
        "py_notes_text": "",
        "statements": {},
        "checklist": [],
        "notes": [],
        "facts": {
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
    """Sidebar provider + API key entry. Returns True once the key is validated."""
    st.sidebar.header("LLM provider")

    if st.session_state.api_key_validated:
        provider_label = PROVIDER_LABELS.get(st.session_state.provider, st.session_state.provider)
        st.sidebar.success(f"{provider_label} validated")
        if st.sidebar.button("Change provider / API key"):
            st.session_state.api_key = ""
            st.session_state.api_key_validated = False
            st.rerun()
        return True

    provider_choice = st.sidebar.radio(
        "Choose a provider",
        [PROVIDER_ANTHROPIC, PROVIDER_OPENAI],
        format_func=lambda p: PROVIDER_LABELS[p],
        index=[PROVIDER_ANTHROPIC, PROVIDER_OPENAI].index(st.session_state.provider),
    )
    st.session_state.provider = provider_choice

    key_input = st.sidebar.text_input(
        f"Enter your {PROVIDER_LABELS[provider_choice]} API key",
        type="password",
        value=st.session_state.api_key,
        help=PROVIDER_HELP[provider_choice] + ". The key is held in session state and never written to disk.",
    )
    if st.sidebar.button("Validate key", type="primary", disabled=not key_input):
        with st.spinner(f"Validating {PROVIDER_LABELS[provider_choice]} API key..."):
            ok, msg = validate_api_key(provider_choice, key_input)
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
    st.sidebar.caption(f"Provider: {PROVIDER_LABELS.get(st.session_state.provider, st.session_state.provider)}")
    st.sidebar.caption(f"Entity: {st.session_state.entity_name or '(not set)'}")
    st.sidebar.caption(f"Type: {st.session_state.entity_type}")


def main() -> None:
    init_session_state()

    st.title("FinStatement AI")
    st.caption("AI-assisted preparation of GAAP-compliant financial statements (FASB and ASC 958)")

    if not render_api_key_gate():
        st.info(
            "Choose a provider (Anthropic Claude or OpenAI GPT) and enter your API key in the sidebar to begin. "
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
