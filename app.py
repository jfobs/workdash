from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import streamlit as st

from src.checks.registry import run_all_checks
from src.parsing.document_hash import content_hash
from src.parsing.pdf_extract import extract_numeric_facts
from src.review.audit_trail import export_audit_trail
from src.review.calculator import calculate_selection, intersecting_facts
from src.review.overrides import build_override
from src.storage.models import CheckStatus, Document
from src.storage.repository import Repository
from src.ui.compare_panels import render_version_compare
from src.ui.components.pdf_overlay import render_pdf_overlay
from src.ui.exports import render_export_button
from src.ui.pages.debug import render_debug_panel
from src.ui.review_panels import render_check_details, render_checklist
from src.ui.sidebar import sidebar_controls

st.set_page_config(layout="wide", page_title="Workdash")
st.title("Workdash — Financial Statement Review")


@st.cache_resource
def get_repo() -> Repository:
    return Repository("workdash.db")


@st.cache_data(show_spinner=False)
def parse_pdf_cached(data: bytes, doc_id: str):
    return extract_numeric_facts(data, doc_id)


def load_fixture_bytes() -> bytes | None:
    fixture_path = Path("fixtures/sample_statement.pdf")
    if fixture_path.exists():
        return fixture_path.read_bytes()
    return None


controls = sidebar_controls()
repo = get_repo()

uploaded = st.file_uploader("Upload one or more financial statement PDFs", type=["pdf"], accept_multiple_files=True)
use_fixture = st.checkbox("Use seeded fixture PDF if available", value=True)

files: list[tuple[str, bytes]] = []
if uploaded:
    files.extend([(f.name, f.read()) for f in uploaded])
if use_fixture:
    fixture = load_fixture_bytes()
    if fixture:
        files.append(("sample_statement.pdf", fixture))

if not files:
    st.info("Upload a PDF to start extraction and checks.")
    st.stop()

documents = []
all_facts = []
for filename, raw in files:
    doc_hash = content_hash(raw)
    doc = Document(document_id=f"doc_{uuid4().hex}", filename=filename, content_hash=doc_hash)
    documents.append(doc)
    all_facts.extend(parse_pdf_cached(raw, doc.document_id))

results = run_all_checks(all_facts, tolerance=controls["tolerance"])
repo.upsert_results(results)

left, right = st.columns([3, 2])
with left:
    st.subheader("PDF Viewer Overlay")
    highlights = []
    if all_facts:
        first_page = min(f.page_number for f in all_facts)
        page_facts = [f for f in all_facts if f.page_number == first_page]
        for fact in page_facts[:25]:
            x0, y0, x1, y1 = fact.bbox
            highlights.append({"x": x0 / 6, "y": y0 / 8, "w": max((x1 - x0) / 6, 1), "h": max((y1 - y0) / 8, 1)})
        render_pdf_overlay(f"Page {first_page}", highlights)

with right:
    st.subheader("Checklist")
    selected = render_checklist(results, controls["status_filter"])
    render_check_details(selected)

    st.subheader("Override")
    if selected is not None:
        o_status = st.selectbox("Override status", [CheckStatus.OVERRIDDEN, CheckStatus.WARNING, CheckStatus.FAIL])
        reason = st.text_area("Reason")
        reviewer = st.text_input("Reviewer initials/name")
        if st.button("Save override"):
            if reason and reviewer:
                decision = build_override(selected.result_id, o_status, reason, reviewer)
                repo.add_override(decision)
                st.success("Override saved.")
            else:
                st.error("Reason and reviewer are required.")

    st.subheader("Drag-box Calculator")
    if all_facts:
        st.caption("Set drag-box bounds in page-space coordinates.")
        c1, c2 = st.columns(2)
        with c1:
            px0 = st.number_input("x0", min_value=0, max_value=1000, value=0, step=1)
            py0 = st.number_input("y0", min_value=0, max_value=1000, value=0, step=1)
        with c2:
            px1 = st.number_input("x1", min_value=0, max_value=1000, value=500, step=1)
            py1 = st.number_input("y1", min_value=0, max_value=1000, value=500, step=1)

        if px1 < px0 or py1 < py0:
            st.error("Invalid bbox: x1/y1 must be greater than or equal to x0/y0.")
            st.stop()

        bbox = (float(px0), float(py0), float(px1), float(py1))
        selected_facts = intersecting_facts(all_facts, bbox)
        signs = [1 for _ in selected_facts]
        if st.button("Calculate selection"):
            calc = calculate_selection(
                documents[0].document_id,
                selected_facts[0].page_number if selected_facts else 1,
                bbox,
                selected_facts,
                signs,
                reviewer="system",
            )
            st.write(calc.model_dump())

if len(documents) >= 2:
    render_version_compare(
        [f for f in all_facts if f.document_id == documents[0].document_id],
        [f for f in all_facts if f.document_id == documents[1].document_id],
        controls["materiality"],
    )

st.subheader("Audit Trail Export")
audit = repo.export_audit()
render_export_button(audit, "audit_trail.json")
if st.button("Write sample export to exports/audit_trail.json"):
    out = export_audit_trail(audit, "exports/audit_trail.json")
    st.success(f"Wrote {out}")

with st.expander("Reviewer Debug Panel"):
    render_debug_panel(all_facts)
