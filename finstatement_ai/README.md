# FinStatement AI

A multi-page Streamlit web app that assists accountants in preparing GAAP-compliant financial statements. It supports both **for-profit (FASB)** and **nonprofit (FASB ASC 958)** entities.

The app is stateless — no database. All work lives in `st.session_state`, and the user downloads a PDF (and a re-uploadable Excel workbook) at the end of each session.

---

## Features

- **API key gate** — enter your Anthropic API key once per session; it's validated with a lightweight Claude call and held only in memory.
- **Source data ingestion** — upload either a prior-year financial statement (Excel/CSV) or a current-year trial balance / grouping report. Auto-detects column headers; falls back to Claude-suggested mappings when no grouping column is present.
- **Editable statements** — Balance Sheet / Statement of Financial Position, Income Statement / Statement of Activities, Cash Flow (indirect or direct), Statement of Changes in Equity, Statement of Functional Expenses. Subtotals and totals recalculate on demand; balance-sheet equilibrium check.
- **GAAP disclosure checklist** — persistent sidebar driven by a rules engine that triggers items based on entity type, statements selected, and account balances (cash, receivables, inventory, PP&E, debt, leases, taxes, net assets, etc.). Users can override any item's status.
- **AI-drafted notes** — Claude generates the full set of triggered notes in formal disclosure language with embedded data tables (debt schedules, lease maturities, net asset rollforwards, etc.). Each note has Redo / Expand / Edit Prompt actions.
- **PDF export** — single professional PDF with cover page, statements, notes, and an optional checklist appendix.
- **Session workbook** — Excel export with sheets `TB_Mapped`, `Statements`, `Notes_Text`, `Notes_Tables` so the session can be re-uploaded next year as a prior-year reference.
- **Reset Session** — sidebar button to clear all state.

---

## Tech stack

- Python 3.11+
- Streamlit (multi-page via the `pages/` folder)
- `anthropic` Python SDK (defaults to `claude-sonnet-4-5`)
- `pandas`, `openpyxl`
- `reportlab` for PDF assembly
- `python-dotenv` for local-dev convenience (the app does not require a `.env` file)

---

## Project structure

```
finstatement_ai/
├── app.py                  # Entry point, API key gate, session init
├── pages/
│   ├── 1_Upload.py         # Entity setup + file upload + preview
│   ├── 2_Statements.py     # Editable statements + checklist sidebar
│   ├── 3_Notes.py          # AI-drafted notes + checklist sidebar
│   ├── 4_Export.py         # Pre-export review + PDF/Excel downloads
├── utils/
│   ├── parser.py           # File ingestion: Excel/CSV -> standardized schema
│   ├── ai_engine.py        # All Claude API calls
│   ├── checklist.py        # GAAP disclosure rules engine
│   ├── pdf_builder.py      # PDF and session-Excel assembly
│   └── mappings.py         # Account grouping maps + statement templates
├── requirements.txt
└── README.md
```

---

## Setup

### 1. Get an Anthropic API key

1. Visit [console.anthropic.com](https://console.anthropic.com) and create an account (or sign in).
2. Go to **API Keys** and click **Create Key**.
3. Copy the key (it starts with `sk-ant-...`). You'll paste it into the app's sidebar — the key is held in `st.session_state` only and never written to disk.

### 2. Run locally

```bash
git clone https://github.com/jfobs/workdash.git
cd workdash/finstatement_ai
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Streamlit will open the app at `http://localhost:8501`. Enter your API key in the sidebar to begin.

### 3. Deploy to Streamlit Community Cloud

1. Push this directory to a GitHub repo.
2. Sign in at [share.streamlit.io](https://share.streamlit.io) with your GitHub account.
3. Click **New app** and select the repo + branch.
4. Set **Main file path** to `finstatement_ai/app.py`.
5. Click **Deploy**. The first build installs from `requirements.txt`.
6. End users enter their own Anthropic API key in the sidebar — you don't need to configure secrets.

---

## Workflow

1. **Upload** — fill in entity name, type (for-profit / nonprofit), basis (accrual / cash), fiscal year end, and select which statements to prepare. Upload a trial balance or prior-year FS. The app parses it, asks Claude to suggest GAAP line-item mappings if needed, and shows an editable preview.
2. **Statements** — review each statement on its own tab. Subtotals and totals recalculate via the **Recalculate Totals** button. The balance sheet flags any out-of-balance condition. Side panel shows the auto-generated GAAP disclosure checklist; users can mark items complete and override status.
3. **Notes** — click **Generate initial notes** to have Claude draft the full set of triggered disclosures. Each note has its own card with editable title, narrative, and (where applicable) embedded data table. Per-note buttons: 🔄 Redo, ➕ Expand, ✏️ Edit Prompt. Add new notes from the standard GAAP catalog or a custom topic.
4. **Export** — review the checklist (incomplete required items show red). Generate the PDF and the re-uploadable session Excel workbook.

---

## Source data formats

Either upload type works. Headers are detected case-insensitively.

### Trial Balance / Grouping Report

| Common columns | Notes |
|---|---|
| `Account Number`, `Account #`, `GL No` | Optional |
| `Account Description`, `Description` | Required |
| `Debit`, `Credit` | If present, used to derive the current-year balance when no balance column exists |
| `CY Balance`, `Balance`, `Ending Balance` | Current-year balance |
| `PY Balance`, `Prior Year` | Prior-year balance for comparative columns |
| `Group`, `Classification`, `FS Group` | Optional — drives statement assignment |
| `Statement` | Optional — explicit statement assignment |
| `Line Item`, `FS Caption` | Optional — explicit line-item mapping |

If `Group` / `Statement` / `Line Item` are all missing, the app asks Claude to suggest mappings and falls back to a keyword/account-number heuristic.

### Prior Year Financial Statement

The Excel workbook this app exports (`<Entity>_SessionData_<FYE>.xlsx`) is itself a valid prior-year input. The parser recognizes the same column headers.

Numeric columns tolerate `$` signs, commas, and parentheses-as-negatives.

---

## Switching to a different Claude model

The default model is `claude-sonnet-4-5`. To use Sonnet 4.6 (the latest) or another model, edit `DEFAULT_MODEL` at the top of `utils/ai_engine.py`. The original spec named `claude-sonnet-4-20250514`, which is the deprecated original Sonnet 4.0 — `claude-sonnet-4-5` is its drop-in replacement.

---

## Notes on cost and rate limits

- The app makes one validation call when the API key is entered.
- Trial-balance mapping is one Claude call (skipped if your file already has a Group/Statement/Line Item column).
- Initial note generation is one large Claude call covering all triggered disclosures.
- Each Redo / Expand / Edit Prompt action is one additional Claude call against a single note.

For very large note sets you may hit your tier's per-minute token limits. Re-run the failing action — the SDK retries 429s with exponential backoff automatically.

---

## License

This is a sample application provided as-is. Validate every figure and disclosure before signing financial statements.
