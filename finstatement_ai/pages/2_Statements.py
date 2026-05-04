"""Page 2 — Editable financial statements with persistent GAAP checklist sidebar."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils import parser as parser_mod
from utils.checklist import (
    REQUIRED, RECOMMENDED, NA,
    build_checklist, merge_checklist, progress, CATEGORIES,
)
from utils.mappings import (
    ENTITY_NONPROFIT,
    STATEMENT_BALANCE_SHEET,
    STATEMENT_INCOME,
    STATEMENT_CASH_FLOW,
    STATEMENT_EQUITY,
    STATEMENT_ACTIVITIES,
    STATEMENT_FINANCIAL_POSITION,
    STATEMENT_FUNCTIONAL_EXPENSES,
    FUNCTIONAL_EXPENSES_PROGRAMS,
    FUNCTIONAL_EXPENSES_CATEGORIES,
    get_statement_structure,
)


st.set_page_config(page_title="Statements — FinStatement AI", layout="wide")


def _require_api_key():
    if not st.session_state.get("api_key_validated"):
        st.warning("Please enter and validate your Anthropic API key on the home page first.")
        st.stop()


def _seed_statement_from_template(stmt_name: str) -> list[dict]:
    """Build initial rows from the standard structure, populated from parsed TB if available."""
    template = get_statement_structure(
        stmt_name,
        st.session_state.entity_type,
        st.session_state.cash_flow_method,
    )
    aggregated = pd.DataFrame()
    if st.session_state.parsed_tb is not None and not st.session_state.parsed_tb.empty:
        aggregated = parser_mod.aggregate_by_line_item(st.session_state.parsed_tb)
    lookup = {}
    if not aggregated.empty:
        for _, r in aggregated.iterrows():
            lookup[str(r["line_item"]).strip().lower()] = (float(r["cy_balance"]), float(r["py_balance"]))
    rows = []
    for line_item, level, kind in template:
        cy, py = (0.0, 0.0)
        if kind == "line":
            cy, py = lookup.get(line_item.lower(), (0.0, 0.0))
        rows.append({
            "line_item": line_item,
            "level": level,
            "kind": kind,
            "cy_balance": cy,
            "py_balance": py,
        })
    return rows


def _seed_functional_expenses() -> list[dict]:
    rows = []
    for cat in FUNCTIONAL_EXPENSES_CATEGORIES:
        row = {"line_item": cat, "level": 0, "kind": "line"}
        for p in FUNCTIONAL_EXPENSES_PROGRAMS:
            row[p] = 0.0
        row["Total"] = 0.0
        rows.append(row)
    rows.append({
        "line_item": "Total expenses",
        "level": 0,
        "kind": "total",
        **{p: 0.0 for p in FUNCTIONAL_EXPENSES_PROGRAMS},
        "Total": 0.0,
    })
    return rows


def _ensure_statements_seeded():
    selected = st.session_state.statements_selected or []
    statements = st.session_state.statements or {}
    for stmt in selected:
        if stmt not in statements or not statements[stmt]:
            if stmt == STATEMENT_FUNCTIONAL_EXPENSES:
                statements[stmt] = _seed_functional_expenses()
            else:
                statements[stmt] = _seed_statement_from_template(stmt)
    # Drop any statements no longer selected.
    for stmt in list(statements.keys()):
        if stmt not in selected:
            statements.pop(stmt, None)
    st.session_state.statements = statements


def _recalculate_subtotals(rows: list[dict]) -> list[dict]:
    """Recompute subtotals and totals using indent-level scoping.

    Rules:
    - A `subtotal` at level L sums everything since the previous subtotal/total
      at level <= L. Within that scope, deeper subtotals absorb lines (their
      value replaces those lines) so we don't double-count.
    - A `total` at level L sums everything since the previous total at level
      <= L. Sibling subtotals at level == L subsume their preceding sibling
      block; their value enters the running total directly.
    - `header` rows are passed through unchanged.

    The scope walk maintains two accumulators per "sibling block":
      sibling_running: deeper subtotals already counted in this block
      sibling_pending: lines not yet absorbed by a deeper subtotal
    A sibling subtotal closes the block — we add its value to the outer total
    and reset both. A deeper subtotal closes the pending lines into running.
    """
    out = [dict(r) for r in rows]
    n = len(out)

    for i in range(n):
        row = out[i]
        kind = row.get("kind", "line")
        if kind not in ("subtotal", "total"):
            continue
        my_level = int(row.get("level", 0) or 0)
        is_total = kind == "total"

        scope_start = 0
        for j in range(i - 1, -1, -1):
            jrow = out[j]
            jkind = jrow.get("kind", "line")
            jlevel = int(jrow.get("level", 0) or 0)
            if is_total:
                if jkind == "total" and jlevel <= my_level:
                    scope_start = j + 1
                    break
            else:
                if jkind in ("subtotal", "total") and jlevel <= my_level:
                    scope_start = j + 1
                    break

        cy = py = 0.0
        sib_running_cy = sib_running_py = 0.0
        sib_pending_cy = sib_pending_py = 0.0

        for j in range(scope_start, i):
            jrow = out[j]
            jkind = jrow.get("kind", "line")
            jlevel = int(jrow.get("level", 0) or 0)
            if jkind == "header":
                continue
            try:
                jcy = float(jrow.get("cy_balance", 0) or 0)
                jpy = float(jrow.get("py_balance", 0) or 0)
            except (TypeError, ValueError):
                continue
            if jkind == "line":
                sib_pending_cy += jcy
                sib_pending_py += jpy
            elif jkind == "subtotal" and jlevel > my_level:
                # Deeper subtotal — absorbs the pending lines into running
                sib_running_cy += jcy
                sib_running_py += jpy
                sib_pending_cy = sib_pending_py = 0.0
            elif jkind == "subtotal" and jlevel == my_level:
                # Sibling subtotal — its value subsumes the current block
                cy += jcy
                py += jpy
                sib_running_cy = sib_running_py = 0.0
                sib_pending_cy = sib_pending_py = 0.0
            # Levels lower than my_level shouldn't appear in scope.

        # Any leftover (no closing sibling subtotal at end of scope)
        cy += sib_running_cy + sib_pending_cy
        py += sib_running_py + sib_pending_py

        row["cy_balance"] = cy
        row["py_balance"] = py

    return out


def _balance_check_balance_sheet(rows: list[dict]) -> tuple[bool, float]:
    """Return (in_balance, difference). difference = total_assets - (total_liab + total_equity)."""
    cy_assets = 0.0
    cy_liab_equity = 0.0
    seen_assets_total = False
    for row in rows:
        line = (row.get("line_item") or "").lower()
        cy = float(row.get("cy_balance", 0) or 0)
        if "total assets" == line:
            cy_assets = cy
            seen_assets_total = True
        elif "total liabilities and" in line:
            cy_liab_equity = cy
    if not seen_assets_total or cy_liab_equity == 0:
        return True, 0.0
    diff = cy_assets - cy_liab_equity
    return abs(diff) < 0.5, diff


def _render_functional_expenses_tab():
    st.markdown(f"### {STATEMENT_FUNCTIONAL_EXPENSES}")
    st.caption("Matrix table — rows are expense categories, columns are programs/functions.")
    rows = st.session_state.statements.get(STATEMENT_FUNCTIONAL_EXPENSES, [])
    if not rows:
        rows = _seed_functional_expenses()
    df = pd.DataFrame(rows)
    column_config = {
        "line_item": st.column_config.TextColumn("Expense Category"),
        "level": None,
        "kind": None,
    }
    for p in FUNCTIONAL_EXPENSES_PROGRAMS + ["Total"]:
        column_config[p] = st.column_config.NumberColumn(p, format="$%.2f")
    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        column_config=column_config,
        key="functional_expenses_editor",
        hide_index=True,
    )
    if st.button("Recalculate Totals", key="recalc_functional"):
        for i, row in edited.iterrows():
            edited.at[i, "Total"] = sum(float(edited.at[i, p] or 0) for p in FUNCTIONAL_EXPENSES_PROGRAMS)
        st.session_state.statements[STATEMENT_FUNCTIONAL_EXPENSES] = edited.to_dict(orient="records")
        st.success("Totals recalculated.")
        st.rerun()
    st.session_state.statements[STATEMENT_FUNCTIONAL_EXPENSES] = edited.to_dict(orient="records")


def _render_standard_statement_tab(stmt_name: str):
    st.markdown(f"### {stmt_name}")
    rows = st.session_state.statements.get(stmt_name, [])
    if not rows:
        rows = _seed_statement_from_template(stmt_name)
    df = pd.DataFrame(rows)

    # Display indentation by prefixing the line_item with spaces matching level.
    df_display = df.copy()
    if "level" in df_display.columns:
        df_display["line_item"] = df_display.apply(
            lambda r: ("    " * int(r.get("level") or 0)) + str(r.get("line_item", "")),
            axis=1,
        )

    column_config = {
        "line_item": st.column_config.TextColumn("Line Item"),
        "cy_balance": st.column_config.NumberColumn("Current Year", format="$%.2f"),
        "py_balance": st.column_config.NumberColumn("Prior Year", format="$%.2f"),
        "level": st.column_config.NumberColumn("Indent Level", min_value=0, max_value=3, step=1),
        "kind": st.column_config.SelectboxColumn("Row Type", options=["line", "subtotal", "total", "header"]),
    }
    edited = st.data_editor(
        df_display,
        num_rows="dynamic",
        use_container_width=True,
        column_config=column_config,
        key=f"editor_{stmt_name}",
        hide_index=True,
    )
    # Strip the indentation prefix back out before storing.
    edited["line_item"] = edited["line_item"].astype(str).str.lstrip()

    cols = st.columns([1, 1, 6])
    with cols[0]:
        if st.button("Recalculate Totals", key=f"recalc_{stmt_name}"):
            recomputed = _recalculate_subtotals(edited.to_dict(orient="records"))
            st.session_state.statements[stmt_name] = recomputed
            st.success("Subtotals and totals recalculated.")
            st.rerun()
    with cols[1]:
        if st.button("Reseed from template", key=f"reseed_{stmt_name}"):
            st.session_state.statements[stmt_name] = _seed_statement_from_template(stmt_name)
            st.success("Reseeded from standard template.")
            st.rerun()

    # Persist edits.
    st.session_state.statements[stmt_name] = edited.to_dict(orient="records")

    # Balance Sheet / SoFP balance check.
    if stmt_name in (STATEMENT_BALANCE_SHEET, STATEMENT_FINANCIAL_POSITION):
        ok, diff = _balance_check_balance_sheet(st.session_state.statements[stmt_name])
        if not ok:
            st.error(
                f"⚠ Out of balance: Assets vs. Liabilities + Equity differ by ${diff:,.2f}. "
                f"Review balances or click Recalculate Totals."
            )
        else:
            st.success("Balance sheet balances.")


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
                        key=f"chk_{item['id']}",
                        label_visibility="collapsed",
                    )
                with cols[1]:
                    badge = {REQUIRED: "🔴", RECOMMENDED: "🟡", NA: "⚪"}[item.get("status", NA)]
                    st.markdown(f"{badge} **{item['title']}**")
                    item["status"] = st.selectbox(
                        "Status",
                        [REQUIRED, RECOMMENDED, NA],
                        index=[REQUIRED, RECOMMENDED, NA].index(item.get("status", NA)),
                        key=f"sts_{item['id']}",
                        label_visibility="collapsed",
                    )


def _build_statements_summary() -> dict:
    """Compact dict of statement -> [{line_item, cy, py}] for AI / checklist."""
    summary = {}
    for stmt_name, rows in (st.session_state.statements or {}).items():
        out_rows = []
        for row in rows or []:
            if row.get("kind") in ("header",):
                continue
            out_rows.append({
                "line_item": row.get("line_item", ""),
                "cy_balance": row.get("cy_balance", 0),
                "py_balance": row.get("py_balance", 0),
            })
        summary[stmt_name] = out_rows
    return summary


def main():
    _require_api_key()
    st.title("Financial Statements")

    if not st.session_state.statements_selected:
        st.warning("Select statements to prepare on the Upload page first.")
        st.stop()

    _ensure_statements_seeded()
    _render_checklist_sidebar()

    tabs = st.tabs(st.session_state.statements_selected)
    for tab, stmt_name in zip(tabs, st.session_state.statements_selected):
        with tab:
            if stmt_name == STATEMENT_FUNCTIONAL_EXPENSES:
                _render_functional_expenses_tab()
            else:
                _render_standard_statement_tab(stmt_name)

    st.info("Continue to the **Notes** page in the left sidebar to draft disclosures.")


main()
