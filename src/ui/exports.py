from __future__ import annotations

import json

import streamlit as st


def render_export_button(payload: list[dict], filename: str) -> None:
    st.download_button(
        label="Download audit trail",
        data=json.dumps(payload, indent=2),
        file_name=filename,
        mime="application/json",
    )
