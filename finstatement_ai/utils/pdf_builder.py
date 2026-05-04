"""PDF assembly using reportlab.

Builds a single professional financial statement package containing:
  1. Cover page
  2. Each financial statement (with comparative columns)
  3. Notes to Financial Statements
  4. Optional GAAP Disclosure Checklist appendix
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Iterable

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


def _styles():
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=22, leading=28, alignment=TA_CENTER, spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=14, leading=20, alignment=TA_CENTER, spaceAfter=8,
        ),
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=16, leading=20, spaceBefore=12, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=16, spaceBefore=10, spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["Normal"], fontName="Helvetica",
            fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=12, alignment=TA_CENTER,
        ),
    }
    return styles


def _fmt_currency(val) -> str:
    try:
        num = float(val)
    except (TypeError, ValueError):
        return str(val) if val not in (None, "") else ""
    if num == 0:
        return "$ -"
    sign = "-" if num < 0 else ""
    return f"{sign}${abs(num):,.0f}"


def _header_footer(canvas, doc, entity_name: str):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    width, _ = LETTER
    canvas.drawString(0.75 * inch, 0.5 * inch, entity_name)
    canvas.drawRightString(width - 0.75 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _build_statement_table(statement_rows: list[dict], current_period_label: str, prior_period_label: str) -> Table:
    """statement_rows: list of dicts with line_item, cy_balance, py_balance, level, kind."""
    header = ["", current_period_label, prior_period_label]
    table_data = [header]
    style_cmds = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
    ]

    for i, row in enumerate(statement_rows, start=1):
        level = int(row.get("level", 0) or 0)
        kind = row.get("kind", "line")
        indent = "    " * level
        label = f"{indent}{row.get('line_item', '')}"
        cy = _fmt_currency(row.get("cy_balance"))
        py = _fmt_currency(row.get("py_balance"))
        if kind == "header":
            table_data.append([label, "", ""])
            style_cmds.append(("FONT", (0, i), (0, i), "Helvetica-Bold", 10))
        elif kind == "subtotal":
            table_data.append([label, cy, py])
            style_cmds.append(("FONT", (0, i), (-1, i), "Helvetica-Bold", 10))
            style_cmds.append(("LINEABOVE", (1, i), (-1, i), 0.5, colors.black))
        elif kind == "total":
            table_data.append([label, cy, py])
            style_cmds.append(("FONT", (0, i), (-1, i), "Helvetica-Bold", 10))
            style_cmds.append(("LINEABOVE", (1, i), (-1, i), 0.5, colors.black))
            style_cmds.append(("LINEBELOW", (1, i), (-1, i), 1.25, colors.black))
        else:
            table_data.append([label, cy, py])

    col_widths = [3.6 * inch, 1.4 * inch, 1.4 * inch]
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))
    return table


def _build_data_table(rows: list[dict], columns: list[str]) -> Table:
    if not rows or not columns:
        return None
    header = list(columns)
    table_data = [header]
    for row in rows:
        out_row = []
        for col in columns:
            val = row.get(col, "")
            if isinstance(val, (int, float)):
                out_row.append(_fmt_currency(val))
            else:
                out_row.append(str(val) if val is not None else "")
        table_data.append(out_row)
    col_count = len(columns)
    available = 6.4 * inch
    col_widths = [available / col_count] * col_count
    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def build_pdf(
    entity_name: str,
    entity_type: str,
    fiscal_year_end: str,
    statements: dict,
    notes: list[dict],
    checklist: list[dict] | None = None,
    include_checklist_appendix: bool = False,
) -> bytes:
    """Assemble the PDF and return raw bytes.

    Args:
        statements: dict of statement_name -> list[{line_item, cy_balance, py_balance, level, kind}]
        notes: list of {title, narrative, table_data, table_columns}
        checklist: list from utils.checklist.build_checklist
        include_checklist_appendix: whether to render the appendix
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title=f"{entity_name} - Financial Statements",
        author="FinStatement AI",
    )

    styles = _styles()
    story: list = []

    # ---------- Cover page ----------
    story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph(entity_name or "Entity Name", styles["title"]))
    story.append(Paragraph("Financial Statements", styles["subtitle"]))
    fye_str = fiscal_year_end if isinstance(fiscal_year_end, str) else str(fiscal_year_end)
    story.append(Paragraph(f"For the year ended {fye_str}", styles["subtitle"]))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(f"({entity_type})", styles["small"]))
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph("See accompanying notes to financial statements.", styles["small"]))
    story.append(PageBreak())

    # ---------- Each financial statement ----------
    cy_label = f"As of/For year ended {fye_str}"
    py_label = "Prior Year"
    for statement_name, rows in (statements or {}).items():
        story.append(Paragraph(entity_name or "", styles["h2"]))
        story.append(Paragraph(statement_name, styles["h1"]))
        story.append(Paragraph(cy_label, styles["small"]))
        story.append(Spacer(1, 0.15 * inch))
        if rows:
            table = _build_statement_table(rows, cy_label, py_label)
            story.append(table)
        else:
            story.append(Paragraph("(No data available for this statement.)", styles["body"]))
        story.append(Spacer(1, 0.3 * inch))
        story.append(Paragraph("See accompanying notes to financial statements.", styles["small"]))
        story.append(PageBreak())

    # ---------- Notes ----------
    if notes:
        story.append(Paragraph("Notes to Financial Statements", styles["h1"]))
        story.append(Spacer(1, 0.1 * inch))
        for note in notes:
            title = note.get("title", "Note")
            narrative = note.get("narrative", "")
            table_data = note.get("table_data") or []
            table_columns = note.get("table_columns") or []
            block: list = [Paragraph(title, styles["h2"])]
            if narrative:
                # Convert linebreaks to <br/> for reportlab paragraphs.
                safe = narrative.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                for para in safe.split("\n\n"):
                    if para.strip():
                        block.append(Paragraph(para.replace("\n", "<br/>"), styles["body"]))
            if table_data and table_columns:
                tbl = _build_data_table(table_data, table_columns)
                if tbl is not None:
                    block.append(Spacer(1, 0.05 * inch))
                    block.append(tbl)
            block.append(Spacer(1, 0.2 * inch))
            story.append(KeepTogether(block))

    # ---------- Optional checklist appendix ----------
    if include_checklist_appendix and checklist:
        story.append(PageBreak())
        story.append(Paragraph("GAAP Disclosure Checklist", styles["h1"]))
        story.append(Spacer(1, 0.1 * inch))
        rows = [["Disclosure", "Category", "Status", "Complete"]]
        for item in checklist:
            rows.append([
                item.get("title", ""),
                item.get("category", ""),
                item.get("status", ""),
                "Yes" if item.get("complete") else "No",
            ])
        col_widths = [3.0 * inch, 1.5 * inch, 1.0 * inch, 0.9 * inch]
        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl)

    on_page = lambda c, d: _header_footer(c, d, entity_name or "")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buffer.seek(0)
    return buffer.read()


def build_session_excel(
    parsed_tb: pd.DataFrame | None,
    statements: dict,
    notes: list[dict],
) -> bytes:
    """Build a re-uploadable Excel workbook with the session data."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        if parsed_tb is not None and not parsed_tb.empty:
            parsed_tb.to_excel(writer, sheet_name="TB_Mapped", index=False)
        else:
            pd.DataFrame(columns=["account_number", "account_description"]).to_excel(
                writer, sheet_name="TB_Mapped", index=False
            )

        statements_rows = []
        for stmt_name, rows in (statements or {}).items():
            for row in rows or []:
                statements_rows.append({
                    "Statement": stmt_name,
                    "line_item": row.get("line_item", ""),
                    "level": row.get("level", 0),
                    "kind": row.get("kind", "line"),
                    "cy_balance": row.get("cy_balance", 0),
                    "py_balance": row.get("py_balance", 0),
                })
        if statements_rows:
            pd.DataFrame(statements_rows).to_excel(writer, sheet_name="Statements", index=False)
        else:
            pd.DataFrame(columns=["Statement", "line_item", "cy_balance", "py_balance"]).to_excel(
                writer, sheet_name="Statements", index=False
            )

        note_text_rows = [{"title": n.get("title", ""), "narrative": n.get("narrative", "")}
                          for n in (notes or [])]
        if note_text_rows:
            pd.DataFrame(note_text_rows).to_excel(writer, sheet_name="Notes_Text", index=False)
        else:
            pd.DataFrame(columns=["title", "narrative"]).to_excel(writer, sheet_name="Notes_Text", index=False)

        note_table_rows = []
        for n in (notes or []):
            title = n.get("title", "")
            for row in (n.get("table_data") or []):
                if isinstance(row, dict):
                    out = {"note_title": title}
                    out.update(row)
                    note_table_rows.append(out)
        if note_table_rows:
            pd.DataFrame(note_table_rows).to_excel(writer, sheet_name="Notes_Tables", index=False)
        else:
            pd.DataFrame(columns=["note_title"]).to_excel(writer, sheet_name="Notes_Tables", index=False)

    buffer.seek(0)
    return buffer.read()
