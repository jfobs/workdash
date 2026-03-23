from __future__ import annotations

import streamlit.components.v1 as components


def render_pdf_overlay(
    page_label: str,
    highlights: list[dict],
    height: int = 520,
) -> None:
    boxes = "".join(
        [
            f"<div class='box' style='left:{h['x']}%;top:{h['y']}%;width:{h['w']}%;height:{h['h']}%;'></div>"
            for h in highlights
        ]
    )
    html = f"""
    <div style="font-family: sans-serif;">
      <div style="margin-bottom: 8px;"><strong>{page_label}</strong></div>
      <div class='canvas'>
        {boxes}
      </div>
    </div>
    <style>
      .canvas {{position: relative; height: 420px; border:1px solid #ddd; background: #fafafa;}}
      .box {{position:absolute; border:2px solid #10b981; background: rgba(16, 185, 129, 0.15);}}
    </style>
    """
    components.html(html, height=height)
