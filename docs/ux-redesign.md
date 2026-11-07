# Phase 7.5 product and implementation plan

The primary journey is Dashboard → readable activity → Investigate → one case workspace → review report → authorized case decision. The four primary destinations are Dashboard, Alerts, Investigations (cases), and Transactions. Accounts, network tooling and administrator audit remain available under Advanced.

The case workspace presents transaction context, plain-language model factors, pre-event account history, connected accounts, evidence, report progress and separate human decisions. Technical identifiers, raw payloads and tool logs are progressively disclosed. Existing deep links continue working.

## Contracts before implementation

- `GET /workspace/dashboard`: actual transaction, actionable-alert, active-case and pending-review counts; priority activity preview.
- `GET /workspace/alerts`: paginated severity-first inbox enriched with amount, account references, persisted score and an existing case link; supports status/severity/search.
- `GET /workspace/transactions`: paginated search/type/account filters with persisted risk and case context.
- `GET /workspace/cases`: readable case list based on linked activity.
- `POST /workspace/alerts/{id}/investigate`: serializes by alert, returns an existing linked case or creates one; attaches missing transaction/score evidence without duplication. No automatic AI run or decision.
- `POST /workspace/cases/{id}/report`: serializes by case and returns the existing run, or starts its first report. Existing API remains available for explicitly starting another run.
- `GET /workspace/cases/{id}`: joined context from real case/alert/transaction/account/score/history records. Detailed evidence, graph and run data reuse the existing endpoints.
- `GET /demo/scenarios`: database-backed, explicitly synthetic guided scenarios with actual record links and model outputs.

All routes require analyst/senior/admin JWTs. Existing role restrictions for decisions/audit are unchanged. No financial write endpoint is added to the browser.

## Dataset isolation and verification

A new demo-batch registry and record-ownership ledger isolate generated accounts, transactions, scores, alerts and prepared cases. Deterministic UUIDs and a batch lock prevent duplicate loads. Reset requires an exact confirmation and refuses external references or active runs. Audit records remain as a trace of loading/resetting. No existing data or training artifacts are deleted.

Generate 500 accounts and 10,000 chronologically ordered transactions over at least 60 simulation days. Use actual pipeline inference and SHAP; model threshold alerts remain separate from clearly labeled demonstration rules. Verify the generator, safety, deduplication, permissions and existing suites against the available local PostgreSQL, then verify the browser against the real API.
