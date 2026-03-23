from __future__ import annotations

import streamlit as st


def sidebar_controls() -> dict:
    st.sidebar.header("Review Controls")
    tolerance = st.sidebar.number_input("Tolerance", min_value=0.0, value=1.0, step=1.0)
    materiality = st.sidebar.number_input("Materiality threshold", min_value=0.0, value=1000.0, step=100.0)
    status_filter = st.sidebar.multiselect(
        "Status filter",
        ["PASS", "FAIL", "WARNING", "UNREVIEWED", "OVERRIDDEN"],
        default=["PASS", "FAIL", "WARNING", "UNREVIEWED", "OVERRIDDEN"],
    )
    return {"tolerance": tolerance, "materiality": materiality, "status_filter": status_filter}
