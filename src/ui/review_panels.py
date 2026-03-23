from __future__ import annotations

import pandas as pd
import streamlit as st

from src.review.tickmarks import tickmark_for_status
from src.storage.models import CheckResult


def render_checklist(results: list[CheckResult], statuses: list[str]) -> CheckResult | None:
    filtered = [r for r in results if r.status.value in statuses]
    if not filtered:
        st.info("No checks for selected filters.")
        return None
    rows = [
        {
            "id": r.result_id,
            "status": r.status.value,
            "tick": tickmark_for_status(r),
            "check": r.check_id,
            "difference": r.calculated_difference,
            "explanation": r.explanation,
        }
        for r in filtered
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    selected_id = st.selectbox("Select check", [r.result_id for r in filtered])
    return next((r for r in filtered if r.result_id == selected_id), None)


def render_check_details(selected: CheckResult | None) -> None:
    if selected is None:
        return
    st.subheader("Check Details")
    st.markdown(f"**Status:** {selected.status.value}")
    st.markdown(f"**Formula:** `{selected.formula}`")
    st.markdown(f"**Narrative:** {selected.narrative}")
    st.markdown(f"**Sources:** {selected.source_fact_ids}")
    st.markdown(f"**Targets:** {selected.target_fact_ids}")
    st.markdown(f"**Difference:** {selected.calculated_difference}")
