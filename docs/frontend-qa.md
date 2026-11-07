# Phase 7.5 verification status — incomplete

Updated 2026-11-07. The real PostgreSQL demo is loaded: 500 owned accounts, 10,000 transactions, 10,000 genuine XGBoost/SHAP assessments, zero model-threshold alerts and eight explicitly labeled demonstration-rule alerts. Existing unrelated operational records were preserved.

- Frontend: 36 tests passed. TypeScript/Vite build passed. ESLint has no errors and four Fast Refresh warnings (two pre-existing, two in the new shared activity component).
- Backend: the latest full PostgreSQL run reported **180 passed, 1 failed, no skips**. The remaining failure expected HTTP 200 from case-decision creation, whose established response is HTTP 201. The assertion is corrected but has not been rerun. Genuine scoring/SHAP parity, reset ownership checks, case concurrency, report deduplication, and ground-truth role isolation ran in this suite.
- Real browser: login, database-backed dashboard counts, four primary destinations, and the first two scenario links/model assessments/graphs passed. The incoming-transfer scenario exposed an exclusive graph cutoff. The UI now requests `event_step + 1` to include the inspected hour; production ML history still excludes the event hour. A graph boundary regression test was added.
- The corrected live-browser run and backend regression rerun were **not executed**: automatic approval review failed because its service usage limit was reached. The review explicitly described this as a review-service failure, not an unsafe-action determination. It must be restored before further elevated live checks.
- Responsive workspace checks, full real-browser report approval/case resolution, final screenshots, and temporary QA-login/server cleanup remain pending. Do not treat historical Phase 7 fixture screenshots as verification of the new workflow.

Resume with the current `qa/live-demo-check.mjs` against the real API, then run the full backend suite with the existing role credentials available privately. Isolated verification services were started on backend 8002/frontend 5175 and Chromium debugging port 9223; user-owned services on 8001/5174 were left untouched. Temporary QA credentials are outside the repository in a mode-600 file and must be deactivated/removed after verification.

---

# Phase 7 verification record

Verified on 2026-11-07. This record covers the local frontend implementation, not production readiness.

## Automated checks actually run

| Check | Observed result |
| --- | --- |
| `npm run build` | Passed strict TypeScript and Vite production build. Routes are split into separate bundles; no oversized-chunk warning. |
| `npm test` | 36 tests passed across 6 files; 0 failed. |
| `npm run lint` | Passed with 0 errors and 2 existing-pattern Fast Refresh warnings (`describeError` and `useAuth` share files with components). |
| `npm run format:check` | Passed. |
| `node qa/browser-check.mjs --all` | Passed in actual installed Chromium 153, using isolated, explicitly labeled synthetic API fixtures. |

Tests cover loading/empty/error/retry states, server pagination and URL filters, mutation cache invalidation, missing score versus unavailable/forbidden score, keyboard table activation, analyst decision restrictions, admin-only audit access, decision confirmation and failure, mocked reports, unresolved citations, report approval separated from case decisions, revision requests, login deep links, logout/expiry cache clearing, stale-token responses, step-zero graph cutoffs, node selection, truncation, exact decimal formatting, and light/dark contrast.

Contrast checks read the actual design tokens: body/metadata/action text and semantic badge labels meet at least 4.5:1 on the tested surfaces; input boundaries and focus indications meet at least 3:1. These targeted checks do not constitute a complete WCAG conformance audit or screen-reader certification.

## Actual browser verification

The first shell/login/overview/alert slice was captured and visually inspected before remaining module implementation. The final pass captured these views at **1440, 1280, 768 and 390px**, with a 950px viewport height:

- Login, overview, alert queue and alert detail.
- Transaction list and transaction side panel.
- Case list and case detail.
- Account directory and account profile.
- Case-scoped investigation picker and investigation report.
- Network Explorer and permission-denied audit view.

All final captures passed the page-overflow assertion. Representative screenshots were visually inspected for each layout family and each required viewport size. Inspection found and corrected cramped card headings and overlapping graph controls on mobile. Dark-mode captures cover overview, network, report, cases, transactions and mobile navigation. Additional captures show alert empty/loading/error states and report/case confirmation dialogs. There are 68 PNGs totaling approximately 4.7 MB in `docs/screenshots/`.

Representative artifacts:

- [Desktop overview](screenshots/overview-1440.png)
- [Tablet alert queue](screenshots/alerts-768.png)
- [Mobile transaction panel](screenshots/transaction-detail-390.png)
- [Mobile network](screenshots/network-390.png)
- [Dark investigation workspace](screenshots/investigation-dark-1440.png)
- [Human case-decision confirmation](screenshots/case-decision-confirmation-1280.png)

The browser workflow exercised real rendered controls: sign in → open critical alert → inspect transaction side panel → close via Escape → create case → attach analyst note → start investigation → approve report → verify no case-decision request occurred → separately record an authorized human case decision. It also verified temporal cutoff propagation to graph/metrics/fund-flow, dark theme, mobile navigation/Escape, and expired-session redirection. No uncaught runtime exception was reported in the final successful pass.

The QA harness creates a new browser tab and injects fixtures only there, labels screenshots, and closes its tab afterward. The fixture module is outside `src/`, never imported by the application, and not included in `dist/`. Application errors never activate fixture data. Earlier QA attempts exposed a Vite dependency-reload error, a browser crash whose crash handler reported a temporary no-space condition, and harness timing/serialization issues; those attempts were not counted as successful verification. The final full pass completed successfully.

## Frontend security review

Reviewed against `.claude/skills/security-reviewer/SKILL.md`:

- JWTs remain in the existing tab-scoped session store, not a bundled credential. No service credential was added to the application.
- Logout and unauthorized responses clear private query data. Successful responses from a previous token are rejected before mutation success handlers can repopulate that cache.
- Admin audit data is not requested by non-admin views. Case decisions are offered only to senior analysts/admins. Backend authorization remains essential and authoritative.
- Report approval and case decision use different endpoints and explicit confirmations. UI approval never directly sets a case to resolved.
- Evidence, analyst notes, reports, tool output and revision feedback are rendered as text, without HTML execution.
- No operational ground-truth fields, banking integrations or invented financial data were added.
- Case/evidence/investigation mutations refresh related queries; mutation retries are disabled.

This is a frontend code/test review, not an independent security sign-off or a fresh verification of backend database grants, deployment configuration or audit durability.

## Remaining verification limits

The configured SentinelAI backend at `localhost:8001` was unavailable. A request to start its existing local environment was rejected, so no live authenticated FastAPI/PostgreSQL golden-path run was completed in this session. Browser results use test fixtures and must not be described as real-backend end-to-end results. No backend/ML test result from an earlier phase was re-measured here. Backend schema/service contracts were inspected directly and frontend API calls were checked against them.

No Docker image was rebuilt or unrelated container stopped. The owned Vite/Chromium QA processes were stopped afterward, and their temporary browser profile/npm cache were removed (about 207 MB). Existing frontend dependencies, Python environment and Chromium installation were reused; Prettier was the only new development dependency. Development-server hosting remains unchanged. Real service integration, deployed CORS/HTTPS/CSP, secret management, full assistive-technology testing and operational requirements still need verification before any production-readiness claim.
