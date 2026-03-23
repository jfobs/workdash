from __future__ import annotations

import pandas as pd
import streamlit as st

from src.storage.models import NumericFact


def render_debug_panel(facts: list[NumericFact]) -> None:
    st.subheader("Debug: Extracted Facts")
    st.dataframe(
        pd.DataFrame([f.model_dump() for f in facts]),
        use_container_width=True,
    )
