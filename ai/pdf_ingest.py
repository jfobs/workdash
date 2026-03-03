from __future__ import annotations

import json
import os
import re
import tempfile
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


def _response_text(response: Any) -> str:
    text = getattr(response, "output_text", "") or ""
    if text.strip():
        return text
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for c in getattr(item, "content", []) or []:
            t = getattr(c, "text", None)
            if t:
                chunks.append(t)
    return "\n".join(chunks)


def _extract_first_amount(text: str) -> float | None:
    patterns = [
        r"\$\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.\d{1,2})?)",
        r"(?:rent|payment|monthly|installment|base\s+rent)[^\d]{0,40}([0-9]{3,}(?:\.\d{1,2})?)",
        r"([0-9]{1,3}(?:,[0-9]{3})+\.\d{2})\s*(?:per\s*month|monthly|mo\b)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def _extract_term_months(text: str) -> int | None:
    mo = re.search(r"(\d{1,3})\s*month", text, flags=re.I)
    if mo:
        return int(mo.group(1))
    yr = re.search(r"(\d{1,2})\s*year", text, flags=re.I)
    if yr:
        return int(yr.group(1)) * 12
    return None


def _extract_date(text: str) -> str | None:
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _fallback_lease_from_text(text: str) -> dict[str, Any] | None:
    amount = _extract_first_amount(text)
    term = _extract_term_months(text)
    if not amount or not term:
        return None
    return {
        "lease_id": "LEASE-1",
        "lease_name": "Extracted Lease",
        "classification": "operating",
        "commencement_date": _extract_date(text) or date.today().isoformat(),
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


def _extract_json_from_text(raw_text: str) -> list[dict[str, Any]]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict) and isinstance(payload.get("leases"), list):
        return payload["leases"]
    return []


def _upload_pdf(client: OpenAI, pdf_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
        tmp.write(pdf_bytes)
        tmp.flush()
        with open(tmp.name, "rb") as fh:
            uploaded = client.files.create(file=fh, purpose="assistants")
    return uploaded.id


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
    payload = json.loads(_response_text(response) or "{}")
    return payload.get("leases", [])


def _extract_with_pdf_file_upload(client: OpenAI, file_id: str, model: str, filename: str) -> list[dict[str, Any]]:
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "OCR and parse this lease PDF. Return JSON object with key 'leases'. "
                            "At minimum include payment_amount and lease_term_months if found."
                        ),
                    },
                    {"type": "input_file", "file_id": file_id, "filename": filename},
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
    payload = json.loads(_response_text(response) or "{}")
    return payload.get("leases", [])


def _extract_with_pdf_file_loose_json(client: OpenAI, file_id: str, model: str, filename: str) -> list[dict[str, Any]]:
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Read this lease PDF and return JSON only: "
                            "{'leases':[{'lease_name':..., 'payment_amount':..., 'lease_term_months':..., 'commencement_date':..., 'classification':...}]}"
                        ),
                    },
                    {"type": "input_file", "file_id": file_id, "filename": filename},
                ],
            }
        ],
    )
    return _extract_json_from_text(_response_text(response))


def _ocr_transcribe_pdf(client: OpenAI, file_id: str, model: str, filename: str) -> str:
    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Transcribe key commercial lease economics from this PDF into plain English. "
                            "Include payment amount, term, start date, frequency, and classification clues."
                        ),
                    },
                    {"type": "input_file", "file_id": file_id, "filename": filename},
                ],
            }
        ],
    )
    return _response_text(response)


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

    if text.strip():
        try:
            normalized = _normalize_extracted_rows(_extract_with_text_prompt(client, text, model))
            if normalized:
                return normalized
        except Exception:
            pass

    try:
        file_id = _upload_pdf(client, pdf_bytes)
    except Exception:
        file_id = ""

    if file_id:
        try:
            normalized = _normalize_extracted_rows(_extract_with_pdf_file_upload(client, file_id, model, filename))
            if normalized:
                return normalized
        except Exception:
            pass

        try:
            normalized = _normalize_extracted_rows(_extract_with_pdf_file_loose_json(client, file_id, model, filename))
            if normalized:
                return normalized
        except Exception:
            pass

        try:
            ocr_text = _ocr_transcribe_pdf(client, file_id, model, filename)
            fallback = _fallback_lease_from_text(ocr_text)
            if fallback:
                return [fallback]
        except Exception:
            pass

    fallback = _fallback_lease_from_text(text) if text.strip() else None
    return [fallback] if fallback else []
