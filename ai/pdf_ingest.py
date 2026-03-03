from __future__ import annotations

import json
import os
from io import BytesIO
from typing import Any

from openai import OpenAI
from pypdf import PdfReader


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "leases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "lease_id": {"type": "string"},
                    "lease_name": {"type": "string"},
                    "classification": {"type": "string", "enum": ["operating", "finance"]},
                    "commencement_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "payment_frequency": {"type": "string", "enum": ["monthly"]},
                    "payment_amount": {"type": "number"},
                    "payment_timing": {"type": "string", "enum": ["EOM", "BOM"]},
                    "lease_term_months": {"type": "integer"},
                    "annual_discount_rate": {"type": "number"},
                    "lease_incentives": {"type": "number"},
                    "initial_direct_costs": {"type": "number"},
                    "prepaid_rent": {"type": "number"},
                    "residual_value_guarantee": {"type": "number"},
                    "variable_payment_amount": {"type": "number"},
                    "nonlease_component_payment": {"type": "number"},
                },
                "required": [
                    "lease_id",
                    "lease_name",
                    "classification",
                    "commencement_date",
                    "payment_frequency",
                    "payment_amount",
                    "payment_timing",
                    "lease_term_months",
                    "annual_discount_rate",
                ],
            },
        }
    },
    "required": ["leases"],
}


def ai_available(api_key: str | None = None) -> bool:
    return bool(api_key or os.getenv("OPENAI_API_KEY"))


def read_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def extract_leases_from_pdf(
    pdf_bytes: bytes,
    model: str = "gpt-5.2",
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    if not ai_available(api_key=api_key):
        raise RuntimeError("OPENAI_API_KEY not set. PDF extraction requires AI.")

    text = read_pdf_text(pdf_bytes)
    if not text.strip():
        return []

    prompt = (
        "Extract lease key terms from this lease contract text. "
        "Return only values that are explicit in the text. "
        "If value missing, use defaults: payment_frequency='monthly', payment_timing='EOM', "
        "lease_incentives=0, initial_direct_costs=0, prepaid_rent=0, residual_value_guarantee=0, "
        "variable_payment_amount=0, nonlease_component_payment=0. "
        "classification must be operating or finance. annual_discount_rate should be decimal like 0.05.\n\n"
        f"LEASE TEXT:\n{text[:120000]}"
    )

    client = OpenAI(api_key=api_key) if api_key else OpenAI()
    response = client.responses.create(
        model=model,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "lease_extraction",
                "schema": EXTRACTION_SCHEMA,
                "strict": True,
            }
        },
    )
    payload = json.loads(response.output_text)
    return payload.get("leases", [])
