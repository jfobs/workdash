# workdash

Production-style Streamlit app for deterministic financial statement review.

## Features

- Upload one or more PDFs and parse numeric facts with provenance (page + bbox).
- Deterministic checks: footing, rollforward, cross-statement ties, note links, repeated value consistency.
- PASS / FAIL / WARNING / UNREVIEWED / OVERRIDDEN status model.
- Reviewer overrides captured additively in SQLite audit trail.
- Drag-box calculator over extracted facts.
- Draft/period comparison panel.
- Downloadable and file-exportable audit trail.
- Reviewer debug panel exposing extracted facts and coordinates.

## Architecture

```text
app.py
src/parsing/
src/checks/
src/review/
src/storage/
src/ui/
  pages/
  components/pdf_overlay/
```

### Rule engine extension notes

1. Add a new deterministic function in `src/checks/<rule>.py` that accepts `list[NumericFact]` and `tolerance`.
2. Return explicit `CheckResult` objects with complete fact id references and formulas.
3. Register it in `src/checks/registry.py` so the UI and persistence layer require no rewrites.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

## Run

```bash
streamlit run app.py
```

## Demo flow

1. Upload financial statement PDFs.
2. Review right-side checklist and click a check for evidence details.
3. Save an override with reason + reviewer.
4. Use drag-box calculator.
5. Download audit trail JSON or write a sample export to `exports/audit_trail.json`.

## Tests

```bash
pytest
```

## Notes on sample fixture

- The app looks for `fixtures/sample_statement.pdf` when **Use seeded fixture PDF** is enabled.
- If the file is missing, the app still works with uploaded PDFs.
