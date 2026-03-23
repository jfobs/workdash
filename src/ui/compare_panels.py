from __future__ import annotations

import pandas as pd
import streamlit as st

from src.storage.models import NumericFact


def render_version_compare(left_facts: list[NumericFact], right_facts: list[NumericFact], threshold: float) -> None:
    left_values = {(f.statement_name, f.period_label, round(f.normalized_value or 0, 2)): f for f in left_facts}
    right_values = {(f.statement_name, f.period_label, round(f.normalized_value or 0, 2)): f for f in right_facts}
    changes = []
    for key in left_values.keys() ^ right_values.keys():
        statement, period, value = key
        if abs(value) >= threshold:
            changes.append({"statement": statement, "period": period, "value": value, "change": "added/removed"})
    st.subheader("Version / Period Comparison")
    st.dataframe(pd.DataFrame(changes), use_container_width=True)
