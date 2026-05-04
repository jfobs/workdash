# workdash

Contains **FinStatement AI** — a Streamlit app that helps accountants prepare GAAP-compliant financial statements for for-profit (FASB) and nonprofit (FASB ASC 958) entities.

The app is stateless — all session data lives in `st.session_state` and the user downloads a PDF and re-uploadable Excel workbook at the end of each session. No database.

See [`finstatement_ai/README.md`](finstatement_ai/README.md) for setup, deployment, and usage.
