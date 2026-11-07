# SentinelAI product analysis and workflows

## Personas and jobs

- Analysts triage model/rule alerts, inspect transaction explanations and account relationships, assemble evidence, and review AI drafts.
- Senior analysts perform the same investigation work and record a reasoned case decision.
- Administrators additionally inspect the audit log. Backend authorization remains authoritative.

## Information architecture and page requirements

Overview prioritizes open critical/high alerts and cases pending review. Alerts provide status, severity and inclusive creation-date filters. Transactions provide server pagination, account/type filters and direct UUID lookup; details expose persisted scores, SHAP and account links. Cases group alerts, evidence and analyst notes, investigation runs and human decisions. Network Explorer starts with an account and exposes bounded, directed neighborhoods, metrics and fund-flow paths at an optional simulation-step cutoff. AI Investigations is case-scoped because no global runs endpoint exists. Audit log is admin-only.

## Critical journey

Sign in → open a critical alert → inspect transaction and persisted explanation → follow an account into Network Explorer → return to alert and create a case → attach server-resolved evidence or an analyst note → move case to investigating → start an AI investigation → inspect execution, citations, findings and uncertainties → approve/reject the report or request revision → senior analyst/admin records a separate case decision with rationale.

Report approval never resolves a case. Mock reports carry an explicit label. Financial amounts are synthetic units: the API provides no currency. Missing scores are distinguished from failed requests. No API error is replaced by sample data.

## API boundaries

There is no aggregate dashboard, time-series, global risk-distribution, global investigation-list, case-history, transaction search/sort or alert-to-case lookup endpoint. Use filtered list totals and clearly bounded views; do not imply sampled data is a population aggregate. Transactions are ordered by simulation step by the server; alerts are newest first. Account reference search is exact. A case timeline can show only recorded creation, linking, update, evidence and decision timestamps, not reconstruct status history.

## Delivery gates

A/B: document analysis and design before wiring screens. C: connect shell/login/overview/alerts. D: run available browser QA at 1440, 1280, 768 and 390px before adding remaining modules. E: connect transactions, cases, graph and AI workspace. F: run automated checks, browser workflows, and document observed limitations.
