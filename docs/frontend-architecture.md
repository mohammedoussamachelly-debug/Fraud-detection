# Frontend architecture

React/TypeScript/Vite with Tailwind semantic tokens; React Router for protected navigation; TanStack Query for asynchronous state; TanStack Table for list rendering; Recharts for scoped analytics; Cytoscape for account networks; Radix for accessible modal/control primitives.

`api/` mirrors the actual FastAPI routes and Pydantic schemas. `features/` owns workflows. `components/` contains repeated layout, data and UI patterns. The application does not require new backend endpoints.

Authentication uses the existing session-scoped JWT store and `/auth/me`. Logout and unauthorized responses clear authenticated query state. Role gates improve presentation; the backend enforces permission on every request. Mutation retries are disabled. Mutations invalidate related list, detail and summary keys. Expected 404s (missing persisted score or decision) have explicit empty states; other failures are surfaced with retry actions.

Read lists use bounded pagination. Do not silently truncate lists or offer sort/filter controls unsupported by the server. Amounts preserve decimal strings in the API and display synthetic units. No service API key is shipped in the UI. AI reports and evidence are rendered as text, never HTML.

Run `npm run build`, `npm test`, and `npm run lint` from `frontend`. Browser QA details and limitations are recorded in `docs/frontend-qa.md`. Reuse installed dependencies and local browsers; no Docker rebuild is required for frontend work.

## Implementation details and verification boundaries

Routes are lazy-loaded so graph/chart libraries are fetched only when needed. The installed TanStack Table v9 adapter is used directly. All successful mutations refresh their affected cache keys; old-token responses are rejected before they can repopulate cleared private cache data. An error boundary provides recovery from render failures.

Overview composes list totals: four severity queries, a pending-review list, a transaction count, seven UTC day counts, and a bounded recent-case/run sample. No financial amounts are aggregated client-side. Decimal amounts retain their cents without floating-point conversion. Query data is not a realtime stream.

`qa/browser-check.mjs` uses an existing Chromium DevTools endpoint on port 9223 with isolated synthetic fixtures injected only into a new QA tab. It is outside `src`, not part of the production build, and labels every screenshot. Run `npm run test:browser` with a local Vite server (default QA URL `http://127.0.0.1:5174`, override `QA_BASE_URL`) and the QA browser already running. No browser download is required. `npm run format:check` verifies Prettier conventions.
