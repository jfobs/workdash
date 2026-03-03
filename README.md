# LeaseWorkbench

LeaseWorkbench is a Streamlit application for ASC 842 lease accounting workflows.

## Features
- Deterministic lease amortization schedules (operating + finance).
- Consolidated monthly views by classification.
- ASC 842 disclosure table generation.
- Audit workbook export with `Data` and `Disclosures - YYYY` sheets.
- Word note disclosure export (`.docx`).
- Optional AI-assisted narrative drafting (numbers remain deterministic).

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
- `lease_id`, `lease_name`, `classification`, `commencement_date`
- `payment_amount`, `payment_timing`, `lease_term_months` (or `end_date`)
- `annual_discount_rate`

## AI mode
Set `OPENAI_API_KEY` in your environment (or Streamlit secrets). AI mode is optional.

## Project structure
- `app.py`: Streamlit UI
- `models.py`: Input models and validation
- `lease_engine.py`: Schedule math engine
- `disclosures.py`: ASC 842 disclosure aggregation
- `exports/excel_export.py`: Excel workbook output
- `exports/docx_export.py`: Word output
- `ai/narratives.py`: OpenAI Responses API calls
- `tests/`: Unit tests
