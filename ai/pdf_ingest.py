from __future__ import annotations

import base64
import json
import os
import re
from datetime import date
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
                    "lease_id": {"type": ["string", "null"]},
                    "lease_name": {"type": ["string", "null"]},
                    "classification": {"type": ["string", "null"], "enum": ["operating", "finance", None]},
                    "commencement_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
                    "payment_frequency": {"type": ["string", "null"], "enum": ["monthly", None]},
                    "payment_amount": {"type": ["number", "null"]},
                    "payment_timing": {"type": ["string", "null"], "enum": ["EOM", "BOM", None]},
                    "lease_term_months": {"type": ["integer", "null"]},
                    "annual_discount_rate": {"type": ["number", "null"]},
                    "lease_incentives": {"type": ["number", "null"]},
                    "initial_direct_costs": {"type": ["number", "null"]},
                    "prepaid_rent": {"type": ["number", "null"]},
                    "residual_value_guarantee": {"type": ["number", "null"]},
                    "variable_payment_amount": {"type": ["number", "null"]},
                    "nonlease_component_payment": {"type": ["number", "null"]},
                },
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


def _extract_first_amount(text: str) -> float | None:
    m = re.search(r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{1,2})?)", text)
    if not m:
        m = re.search(r"(?:rent|payment)[^\d]{0,20}([0-9]{3,}(?:\.\d{1,2})?)", text, flags=re.I)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _extract_term_months(text: str) -> int | None:
    mo = re.search(r"(\d{1,3})\s*month", text, flags=re.I)
    if mo:
        return int(mo.group(1))
    yr = re.search(r"(\d{1,2})\s*year", text, flags=re.I)
    if yr:
        return int(yr.group(1)) * 12
    return None


def _fallback_lease_from_text(text: str) -> dict[str, Any] | None:
    amount = _extract_first_amount(text)
    term = _extract_term_months(text)
    if not amount or not term:
        return None
    return {
        "lease_id": "LEASE-1",
        "lease_name": "Extracted Lease",
        "classification": "operating",
        "commencement_date": date.today().isoformat(),
        "payment_frequency": "monthly",
        "payment_amount": amount,
        "payment_timing": "EOM",
        "lease_term_months": term,
        "annual_discount_rate": 0.05,
        "lease_incentives": 0.0,
        "initial_direct_costs": 0.0,
        "prepaid_rent": 0.0,
        "residual_value_guarantee": 0.0,
        "variable_payment_amount": 0.0,
        "nonlease_component_payment": 0.0,
    }


def _normalize_extracted_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        payment_amount = row.get("payment_amount")
        lease_term = row.get("lease_term_months")
        if payment_amount in (None, "") or lease_term in (None, ""):
            continue
        payment_amount = float(payment_amount)
        lease_term = int(lease_term)
        if payment_amount <= 0 or lease_term <= 0:
            continue

        normalized.append(
            {
                "lease_id": (row.get("lease_id") or f"LEASE-{i}"),
                "lease_name": (row.get("lease_name") or f"Extracted Lease {i}"),
                "classification": row.get("classification") or "operating",
                "commencement_date": row.get("commencement_date") or date.today().isoformat(),
                "payment_frequency": row.get("payment_frequency") or "monthly",
                "payment_amount": payment_amount,
                "payment_timing": row.get("payment_timing") or "EOM",
                "lease_term_months": lease_term,
                "annual_discount_rate": float(row.get("annual_discount_rate") or 0.05),
                "lease_incentives": float(row.get("lease_incentives") or 0),
                "initial_direct_costs": float(row.get("initial_direct_costs") or 0),
                "prepaid_rent": float(row.get("prepaid_rent") or 0),
                "residual_value_guarantee": float(row.get("residual_value_guarantee") or 0),
                "variable_payment_amount": float(row.get("variable_payment_amount") or 0),
                "nonlease_component_payment": float(row.get("nonlease_component_payment") or 0),
            }
        )
    return normalized


def _extract_with_text_prompt(client: OpenAI, text: str, model: str) -> list[dict[str, Any]]:
    prompt = (
        "Extract lease key terms from this lease contract text. "
        "Return best-effort structured lease rows even if some fields are uncertain. "
        "Map terms like base rent/monthly rent to payment_amount. "
        "Map initial term (years or months) to lease_term_months. "
        "Map start/commencement date to commencement_date in YYYY-MM-DD. "
        "If document is equipment/vehicle lease, still extract fixed payment and term. "
        "Use only 'operating' or 'finance' classification.\n\n"
        f"LEASE TEXT:\n{text[:120000]}"
    )

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


def _extract_with_pdf_file(client: OpenAI, pdf_bytes: bytes, model: str, filename: str) -> list[dict[str, Any]]:
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "This is a lease PDF, potentially scanned/image-heavy. "
                            "OCR the document and extract lease rows with payment_amount and lease_term_months when available."
                        ),
                    },
                    {
                        "type": "input_file",
                        "filename": filename,
                        "file_data": f"data:application/pdf;base64,{b64}",
                    },
                ],
            }
        ],
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


def extract_leases_from_pdf(
    pdf_bytes: bytes,
    model: str = "gpt-5.2",
    api_key: str | None = None,
    filename: str = "lease.pdf",
) -> list[dict[str, Any]]:
    if not ai_available(api_key=api_key):
        raise RuntimeError("OPENAI_API_KEY not set. PDF extraction requires AI.")

    client = OpenAI(api_key=api_key) if api_key else OpenAI()
    text = read_pdf_text(pdf_bytes)

    candidates: list[dict[str, Any]] = []
    if text.strip():
        try:
            candidates = _extract_with_text_prompt(client, text, model)
        except Exception:
            candidates = []

    normalized = _normalize_extracted_rows(candidates)
    if normalized:
        return normalized

    # If extracted text is sparse or model produced unusable rows, try direct PDF OCR path.
    try:
        file_candidates = _extract_with_pdf_file(client, pdf_bytes, model, filename)
        normalized = _normalize_extracted_rows(file_candidates)
        if normalized:
            return normalized
    except Exception:
        pass

    # Last deterministic fallback from any extracted text.
    fallback = _fallback_lease_from_text(text) if text.strip() else None
    return [fallback] if fallback else []
