# LeaseWorkbench

LeaseWorkbench is a Streamlit application for ASC 842 lease accounting workflows.

## Features
- Deterministic lease amortization schedules (operating + finance).
- Rent escalation support via annual escalation inputs and explicit rent step JSON (period-based).
- Consolidated monthly views by classification.
- ASC 842 disclosure table generation.
- Audit workbook export with `Data` and `Disclosures - YYYY` sheets.
- Word note disclosure export (`.docx`).
- Optional AI-assisted narrative drafting (numbers remain deterministic).
- PDF lease contract ingestion + AI extraction of key lease terms into the portfolio table.

## Setup
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```bash
streamlit run app.py
```

## Tests
```bash
pytest -q
```

## Input template
Use the **Download template** button in the app sidebar. Required fields:

You can also upload one or more lease contract PDFs in the sidebar and click **Extract leases from PDFs** (requires `OPENAI_API_KEY`). The extractor now uses a 3-step approach: text extraction + AI parse, then direct PDF OCR/file parsing with AI for scanned docs, then regex fallback for rent/term if needed.

For stepped rents / escalations:
- `escalation_rate_annual` + `escalation_interval_months` (e.g., 0.03 every 12 months), or
- `rent_steps_json` such as `{"1":2500,"13":2575,"25":2652.25}` where keys are period numbers.
- `lease_id`, `lease_name`, `classification`, `commencement_date`
- `payment_amount`, `payment_timing`, `lease_term_months` (or `end_date`)
- `annual_discount_rate`

## AI mode
AI mode is optional. You can either:
- set `OPENAI_API_KEY` in your environment (or Streamlit secrets), or
- enter the key in the left sidebar using **OpenAI API Key**.

You can also choose the model in the sidebar with **OpenAI model**.

## Project structure
- `app.py`: Streamlit UI with top tab navigation (Dashboard, Lease Detail, Journal Entries, Disclosures, Import/Export)
- `models.py`: Input models and validation
- `lease_engine.py`: Schedule math engine
- `disclosures.py`: ASC 842 disclosure aggregation
- `exports/excel_export.py`: Excel workbook output
- `exports/docx_export.py`: Word output
- `ai/narratives.py`: OpenAI Responses API calls
- `tests/`: Unit tests
