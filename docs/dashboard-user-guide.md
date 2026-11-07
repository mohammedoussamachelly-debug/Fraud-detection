# SentinelAI dashboard user guide

## Open the workspace

Start the existing FastAPI/Postgres development environment using the project README, then run `npm run dev` in `frontend/`. `VITE_API_BASE_URL` defaults to `http://localhost:8001/api/v1`; set it before starting/building when your backend uses another address. The backend must allow the browser's exact origin in `CORS_ORIGINS`. No accounts or financial activity are created by opening the dashboard.

Sign in with an existing SentinelAI user. Protected links return to the requested page after login. Sign out from the account menu. Session tokens are scoped to the browser tab; expired sessions return to login. The header provides a persistent light/dark theme toggle. On smaller screens, the navigation button opens the menu; Escape closes it. Use the keyboard skip link to reach the content.

All amounts represent synthetic units; the API does not identify a currency. Displayed times use your browser's local timezone. Date-range filters use inclusive UTC dates, and graph cutoffs use simulation steps rather than calendar dates.

## Triage and inspect

1. Open **Overview** for the open-alert queue, cases awaiting human review, and total ingested transactions. The priority preview takes critical alerts before high, medium and low alerts; alerts within a severity are newest first.
2. Open **Alerts** and filter by status, severity or creation date. The queue uses backend pagination and newest-first ordering. Press Enter/Space on a focused table row to open its details.
3. Inspect the transaction, model version, threshold and stored SHAP contributions. A missing score/explanation is stated explicitly. API failures have an error state and retry action.
4. Follow a transaction reference to its side panel. Inspect balances and accounts; Escape closes the panel. Transactions support account/type filters and direct UUID lookup. Their server order is simulation step ascending.
5. Follow an account to its profile, transactions or **Network Explorer**. The account directory searches exact external references.

Overview charts show open-alert severity and seven days of alert intake. They are not a distribution of all transaction risk scores. Today is partial. Recent investigation activity is explicitly limited to the newest five cases; use case investigation history for all runs in a case. Overview data refreshes when queries become stale and the window regains focus; it is not a streaming feed.

## Build and resolve a case

From an alert, select **Create case** and its priority. The **Cases** list supports status and “Assigned to me” filters and displays assignee IDs where names are unavailable. Open a case to set priority, assign yourself or move it through the server-supported lifecycle.

Use **Evidence & notes → Attach evidence** to add a backend-resolved record or analyst note. Transactions require a transaction UUID. Risk-score and SHAP evidence require the persisted **risk score UUID**, displayed in the risk assessment. Graph/history evidence requires an account UUID. Graph snapshots support an optional step cutoff and bounded traversal settings. Expand “Inspect evidence payload” to inspect the recorded snapshot. Evidence and runs have separate pagination.

**History** presents available recorded milestones, including case creation, alert links, latest update, decision and closure. It does not reconstruct a full status-change audit trail. Administrators can separately access **Audit log** with action/date filters.

In **Investigations**, start a run and inspect its execution timeline, tool calls, collected evidence references, findings, uncertainties and recommended next step. Running investigations poll for updates. Mock reports have a conspicuous **Mock AI report** label. A citation can focus its collected evidence entry; an unresolved reference is explicitly marked.

Choose **Approve report**, **Reject report**, or provide revision feedback. Each action has a confirmation step. Report approval is separate from deciding a case and does not resolve it.

A **senior analyst or admin** can use the case's **Decision** tab while the case is investigating or pending review. Choose a decision, write at least ten non-whitespace-trimmed characters of rationale, review the confirmation, and record it. This records the human decision and resolves the case. A resolved case may then be closed. Analysts can read existing decisions but cannot record one.

## Investigate a network

Enter an account UUID, choose 1–4 neighborhood hops and optionally an inclusive “as of” step. The same cutoff is applied to the neighborhood, selected-account metrics and fund-flow paths. Arrowheads indicate transaction direction. Select a node with the pointer or its labeled account button below the graph. Use **Fit graph** after panning/zooming.

Selected-account metrics show transaction counts, counterparties and structural signals. Fund-flow paths use up to three hops and five branches and link back to transaction details. Truncation is always visible; an incomplete graph is not presented as the full network. Structural patterns do not prove fraud.

## Current limitations

- No backend aggregate risk distribution, arbitrary transaction search/sorting, global investigation feed, bulk alert update, or reverse alert-to-case lookup exists. The UI does not invent these operations.
- Existing cases can be opened from the case list; the alert page cannot discover all linked cases through the current API.
- The synthetic-fixture browser QA is separate from live backend verification. See `frontend-qa.md` for the exact verification scope.
- This is a development application. Deployment hardening, HTTPS, CSP, secret management and operational/security validation remain prerequisites to any production claim.
