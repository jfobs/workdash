"""Page 3 — Notes & Disclosures editor with the same persistent checklist sidebar."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.ai_engine import (
    generate_all_notes,
    regenerate_note,
    generate_single_note,
)
from utils.checklist import (
    REQUIRED, RECOMMENDED, NA,
    build_checklist, merge_checklist, progress,
    required_note_titles, STANDARD_NOTE_CATALOG, CATEGORIES,
)


st.set_page_config(page_title="Notes — FinStatement AI", layout="wide")


def _require_api_key():
    if not st.session_state.get("api_key_validated"):
        st.warning("Please enter and validate your Anthropic API key on the home page first.")
        st.stop()


def _build_statements_summary() -> dict:
    summary = {}
    for stmt_name, rows in (st.session_state.statements or {}).items():
        out = []
        for row in rows or []:
            if row.get("kind") == "header":
                continue
            out.append({
                "line_item": row.get("line_item", ""),
                "cy_balance": row.get("cy_balance", 0),
                "py_balance": row.get("py_balance", 0),
            })
        summary[stmt_name] = out
    return summary


def _render_checklist_sidebar():
    facts = {
        "entity_type": st.session_state.entity_type,
        "statements_selected": st.session_state.statements_selected,
        "statements_summary": _build_statements_summary(),
        **st.session_state.facts,
    }
    rebuilt = build_checklist(facts)
    st.session_state.checklist = merge_checklist(st.session_state.checklist, rebuilt)

    st.sidebar.subheader("GAAP Disclosure Checklist")
    completed, total = progress(st.session_state.checklist)
    if total:
        st.sidebar.progress(completed / total, text=f"{completed} of {total} required disclosures complete")
    else:
        st.sidebar.caption("No required disclosures triggered yet.")

    by_category = {}
    for item in st.session_state.checklist:
        by_category.setdefault(item["category"], []).append(item)
    for category in CATEGORIES:
        items = by_category.get(category, [])
        if not items:
            continue
        with st.sidebar.expander(category, expanded=False):
            for item in items:
                cols = st.columns([1, 5])
                with cols[0]:
                    item["complete"] = st.checkbox(
                        " ",
                        value=item.get("complete", False),
                        key=f"chk_n_{item['id']}",
                        label_visibility="collapsed",
                    )
                with cols[1]:
                    badge = {REQUIRED: "🔴", RECOMMENDED: "🟡", NA: "⚪"}[item.get("status", NA)]
                    st.markdown(f"{badge} **{item['title']}**")
                    item["status"] = st.selectbox(
                        "Status",
                        [REQUIRED, RECOMMENDED, NA],
                        index=[REQUIRED, RECOMMENDED, NA].index(item.get("status", NA)),
                        key=f"sts_n_{item['id']}",
                        label_visibility="collapsed",
                    )


def _generate_initial_notes_button():
    if st.session_state.notes:
        return
    st.info("No notes drafted yet. Click the button below to generate the initial draft for all triggered disclosures.")
    if st.button("Generate initial notes", type="primary"):
        titles = required_note_titles(st.session_state.checklist) or [
            "Summary of Significant Accounting Policies",
            "Nature of Operations",
            "Subsequent Events",
        ]
        with st.spinner("Drafting notes — this may take a moment..."):
            try:
                notes = generate_all_notes(
                    provider=st.session_state.provider,
                    api_key=st.session_state.api_key,
                    entity_name=st.session_state.entity_name or "the Entity",
                    entity_type=st.session_state.entity_type,
                    fiscal_year_end=str(st.session_state.fiscal_year_end or ""),
                    statements_summary=_build_statements_summary(),
                    required_notes=titles,
                    prior_year_notes_text=st.session_state.py_notes_text or "",
                )
            except Exception as e:
                st.error(f"Note generation failed: {e}")
                return
        if not notes:
            st.error("The LLM did not return any notes. Try again or adjust the checklist.")
            return
        # Ensure Note 1 is always Summary of Significant Accounting Policies.
        # If the model returned it, move it to the front; otherwise prepend.
        sigacct_idx = next((i for i, n in enumerate(notes) if "significant accounting" in n.get("title", "").lower()), None)
        if sigacct_idx is None:
            notes.insert(0, {
                "title": "Note 1 - Summary of Significant Accounting Policies",
                "narrative": "[CONFIRM: Significant accounting policies disclosure was not generated. Click Redo on this note to regenerate.]",
                "table_data": [],
                "table_columns": [],
            })
        elif sigacct_idx != 0:
            note = notes.pop(sigacct_idx)
            notes.insert(0, note)
        st.session_state.notes = notes
        st.success(f"Drafted {len(notes)} notes.")
        st.rerun()


def _render_note_card(idx: int, note: dict):
    title = note.get("title", f"Note {idx + 1}")
    with st.expander(title, expanded=(idx == 0)):
        new_title = st.text_input(
            "Note title",
            value=title,
            key=f"note_title_{idx}",
        )
        new_narrative = st.text_area(
            "Narrative",
            value=note.get("narrative", ""),
            key=f"note_narrative_{idx}",
            height=300,
        )
        # Table editor (if applicable).
        table_data = note.get("table_data") or []
        table_columns = note.get("table_columns") or []
        if table_columns:
            df = pd.DataFrame(table_data, columns=table_columns)
            edited = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                key=f"note_table_{idx}",
                hide_index=True,
            )
            note["table_data"] = edited.to_dict(orient="records")
            note["table_columns"] = list(edited.columns)
        elif table_data:
            cols = list(table_data[0].keys()) if table_data else []
            df = pd.DataFrame(table_data, columns=cols)
            edited = st.data_editor(
                df,
                num_rows="dynamic",
                use_container_width=True,
                key=f"note_table_{idx}",
                hide_index=True,
            )
            note["table_data"] = edited.to_dict(orient="records")
            note["table_columns"] = list(edited.columns)

        note["title"] = new_title
        note["narrative"] = new_narrative

        cols = st.columns([1, 1, 1, 1, 4])
        with cols[0]:
            if st.button("🔄 Redo", key=f"redo_{idx}"):
                _regen_note(idx, mode="redo")
        with cols[1]:
            if st.button("➕ Expand", key=f"expand_{idx}"):
                _regen_note(idx, mode="expand")
        with cols[2]:
            with st.popover("✏️ Edit Prompt"):
                instr = st.text_area(
                    "Custom instruction",
                    key=f"prompt_{idx}",
                    placeholder="e.g., 'Add ASC 326 CECL disclosures and a 5-year vintage table.'",
                )
                if st.button("Apply instruction", key=f"apply_prompt_{idx}"):
                    _regen_note(idx, mode="custom", instruction=instr)
        with cols[3]:
            if st.button("🗑 Delete", key=f"del_{idx}"):
                st.session_state.notes.pop(idx)
                st.rerun()


def _regen_note(idx: int, mode: str, instruction: str = "") -> None:
    note = st.session_state.notes[idx]
    with st.spinner("Regenerating note..."):
        try:
            updated = regenerate_note(
                provider=st.session_state.provider,
                api_key=st.session_state.api_key,
                entity_name=st.session_state.entity_name or "the Entity",
                entity_type=st.session_state.entity_type,
                note_title=note.get("title", ""),
                statements_summary=_build_statements_summary(),
                instruction=instruction,
                mode=mode,
                existing_narrative=note.get("narrative", ""),
            )
        except Exception as e:
            st.error(f"Regeneration failed: {e}")
            return
    st.session_state.notes[idx] = updated
    st.success("Note regenerated.")
    st.rerun()


def _add_note_section():
    st.divider()
    with st.expander("➕ Add a new note"):
        topic = st.selectbox(
            "Standard GAAP disclosure",
            ["(custom topic)"] + STANDARD_NOTE_CATALOG,
        )
        custom_topic = ""
        if topic == "(custom topic)":
            custom_topic = st.text_input("Custom note topic")
        if st.button("Generate note"):
            chosen = custom_topic if topic == "(custom topic)" else topic
            if not chosen:
                st.error("Choose or enter a topic first.")
                return
            with st.spinner("Generating note..."):
                try:
                    note = generate_single_note(
                        provider=st.session_state.provider,
                        api_key=st.session_state.api_key,
                        entity_name=st.session_state.entity_name or "the Entity",
                        entity_type=st.session_state.entity_type,
                        note_topic=chosen,
                        statements_summary=_build_statements_summary(),
                    )
                except Exception as e:
                    st.error(f"Generation failed: {e}")
                    return
            st.session_state.notes.append(note)
            st.success(f"Added note: {note.get('title', chosen)}")
            st.rerun()


def main():
    _require_api_key()
    st.title("Notes & Disclosures")

    if not st.session_state.statements:
        st.warning("Build your financial statements first on the Statements page.")
        st.stop()

    _render_checklist_sidebar()

    left, right = st.columns([3, 1])
    with left:
        _generate_initial_notes_button()
        if st.session_state.notes:
            for idx, note in enumerate(st.session_state.notes):
                _render_note_card(idx, note)
        _add_note_section()
    with right:
        st.markdown("**Tips**")
        st.caption("• Use **Redo** for a fresh take, **Expand** to add depth, and **Edit Prompt** for surgical edits.")
        st.caption("• `[CONFIRM: ...]` markers flag figures or facts the AI couldn't derive — fill them in before exporting.")
        st.caption("• Note 1 is always Summary of Significant Accounting Policies.")
    st.info("Continue to the **Export** page when notes are ready.")


main()
