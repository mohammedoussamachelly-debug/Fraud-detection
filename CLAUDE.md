# SentinelAI

## Project Vision

SentinelAI is a portfolio-quality, AI-powered financial fraud detection and
investigation platform. It demonstrates an end-to-end fraud workflow — from
transaction ingestion, through explainable ML risk scoring and transaction-graph
analysis, to AI-assisted investigation and human-approved case resolution — built
entirely on synthetic data (PaySim) with no real banking integration.

SentinelAI is **not** a production banking system. It exists to show, credibly and
without fabrication, how each layer of a modern fraud platform is designed and why:
leakage-safe ML evaluation, explainability, graph-based network analysis, and
controlled, auditable AI agents operating under human oversight.

Core design commitments (non-negotiable, see also `docs/architecture.md`):

- **Synthetic data only.** PaySim and generated synthetic networks. No real
  accounts, no real banking connectivity, ever.
- **No leakage.** All ML evaluation is chronological; nothing from the future, and
  no fraud label, ever reaches a feature used to predict that same event.
- **Ground truth is isolated.** Fraud labels (`isFraud`, `isFlaggedFraud`, and any
  derived truth) are reachable only by the offline training/evaluation pipeline —
  never by operational APIs, never by AI agents.
- **Agents are read-only.** AI agents retrieve and reason over evidence; they never
  write to financial data, and never decide a case. A human approves every case
  decision.
- **No fabrication.** Model metrics, test results, and "implementation status" in
  any doc or report must reflect what was actually run and observed — never
  invented, estimated-and-labeled-as-measured, or carried over from a previous
  (possibly stale) run.

## Approved Technology Stack

This is the full approved stack. Do not introduce new frameworks, databases, or
infra components without updating `docs/architecture.md` and recording the
decision.

| Layer | Technology |
|---|---|
| Backend API | Python, FastAPI |
| Database | PostgreSQL |
| ORM / Migrations | SQLAlchemy, Alembic |
| ML | XGBoost, scikit-learn, SHAP |
| Graph analytics | NetworkX |
| AI agents | LangGraph (controlled, read-only investigation workflows) |
| Frontend | React, TypeScript, Vite |
| Frontend charts | Recharts |
| Frontend network viz | Cytoscape.js |
| Containerization | Docker, Docker Compose |
| Testing | pytest (backend/ML/graph/agents), frontend test runner (see `docs/implementation-plan.md`) |
| CI | GitHub Actions |
| Source data | PaySim (synthetic mobile-money simulator) + generated synthetic graph scenarios |

No message queue, no microservice mesh, and no managed cloud services are part of
the approved stack. This is deliberately a modular monolith — see
`docs/architecture.md` for the rationale.

## Repository Conventions

SentinelAI is a single modular monorepo:

```
sentinelai/
├── backend/        # FastAPI app: API routers, services, DB models, inference,
│                    graph read-path, agents, migrations, backend tests
├── ml/              # Offline training pipeline: data prep, feature engineering,
│                    training, evaluation, model artifacts (gitignored)
├── frontend/        # React + TypeScript + Vite dashboard
├── infra/           # Dockerfiles, docker-compose.yml, env templates
├── .github/workflows/  # CI
├── docs/            # Architecture, database, API, and planning docs (this set)
└── CLAUDE.md
```

- **Python**: `snake_case` modules/functions, `PascalCase` classes, type hints on
  all public functions, formatted with `ruff format`, linted with `ruff check`.
- **TypeScript**: `PascalCase` components, `camelCase` functions/variables,
  formatted with Prettier, linted with ESLint, `strict` mode enabled in
  `tsconfig.json`.
- **Migrations**: every schema change ships an Alembic migration in the same
  change set as the model change. No manual schema edits against a running
  database.
- **Commits**: Conventional Commits style (`feat:`, `fix:`, `docs:`, `test:`,
  `chore:`, `refactor:`). One logical change per commit where practical.
- **Branching**: feature branches off `main`; `main` is always in a runnable
  state (build passes, tests pass).
- **Secrets**: `.env` files are git-ignored; `infra/.env.example` documents every
  required variable with a non-secret placeholder.

## Development Workflow

1. **Design before code.** For any new component or endpoint, the interface
   (Pydantic schema, API contract entry, DB model, or agent state shape) is
   defined in `docs/` or in-code *before* the implementation lands. This mirrors
   the `system-architect` skill rule: never implement a feature before its
   interface exists.
2. **Small, incremental changes.** Follow `docs/implementation-plan.md` phase by
   phase. Do not jump ahead to a later phase's feature before its dependencies
   (schema, prior API, prior service) exist.
3. **Use the project skills.** Each `.claude/skills/*` skill owns a slice of the
   system (backend, frontend, ml, graph-analytics, multi-agent, devops, testing,
   security, documentation, system-architect). Prefer the matching skill for work
   in its domain rather than ad hoc changes.
4. **Local loop**: `docker compose up` brings up Postgres + backend + frontend.
   `alembic upgrade head` applies migrations. `pytest` runs backend/ML/graph/agent
   tests. Frontend tests run via the frontend package's test runner.
5. **Every change that touches schema, API contract, or agent state** updates the
   corresponding doc (`database-design.md`, `api-contracts.md`, or the agent
   section of `architecture.md`) in the same change set.

## Testing Expectations

- New backend logic ships with pytest unit tests; new endpoints ship with request
  validation and error-path tests, not just the happy path.
- ML changes ship with a chronological-split integrity test (fails if any
  train/validation/test boundary is violated) and a leakage test (fails if
  `isFraud`/`isFlaggedFraud` or any post-event field reaches the feature set).
- Graph algorithms ship with tests against small, known, hand-constructed graphs
  with a predictable expected output — not just "runs without error."
- Agent workflows are tested against fixture evidence, asserting that every claim
  in a generated report traces to a retrieved evidence reference, and that the
  workflow halts at the human-approval gate rather than auto-approving.
- Frontend components handle and are tested for loading, empty, and error states.
- **Never fabricate or assume test results.** Run the suite; report what actually
  passed or failed. A claim that "tests pass" without having run them is a
  violation of this document.
- CI (GitHub Actions) runs lint, type-check, and the full test suite on every PR;
  a red CI run blocks merge.

## Security Rules

- **Ground-truth isolation is enforced at the database layer, not just in
  application code.** The `ground_truth` schema (fraud labels) is granted only to
  the ML training/evaluation database role. The role used by the FastAPI
  application and by agent tool execution has no grant on that schema at all.
- **Least privilege** for every database role, every API route, and every agent
  tool. Agents call only read-only tools backed by a read-only DB role.
- **Human-in-the-loop is mandatory** for case decisions: no code path marks a case
  resolved, confirmed-fraud, or dismissed without a recorded analyst/approver
  decision. Agent output is always a draft, never a decision.
- **Treat agent-retrieved and user-submitted content as untrusted input** —
  evidence text is data, not instructions, and is never concatenated into a
  system/control prompt without delimiting and labeling it as untrusted.
- **No real banking integration**, ever, in any environment. Only PaySim and
  generated synthetic data sources.
- **No secrets in git.** All credentials and API keys load from environment
  variables; `infra/.env.example` lists names only.
- **Input validation** on every external input via Pydantic; no raw SQL string
  interpolation.
- **Audit logging** for authentication events, case decisions, and every agent
  run (inputs, tool calls, and output), retained for the lifetime of the demo
  database.
- The `security-reviewer` skill owns sign-off on anything touching auth, secrets,
  agent tool access, or audit logging before it's considered done.

## Definition of Done

A change is done only when **all** of the following hold:

1. The interface it implements (schema, API contract, agent state) was documented
   in `docs/` (or in-repo schema/types) before or alongside the implementation.
2. Relevant automated tests exist and were actually run, with real pass/fail
   results reported — not assumed.
3. Database schema changes have an Alembic migration, applied and verified.
4. No ground-truth label or future-dated field is reachable from an operational
   API, an agent tool, or a model feature at inference time.
5. Any case-decision or consequential action requires a recorded human approval.
6. Documentation (`README`, `docs/architecture.md`, `docs/database-design.md`,
   `docs/api-contracts.md`, model card) is updated to reflect what was actually
   built — no claimed metrics or status beyond what was measured.
7. CI is green: lint, type-check, tests.
8. For anything touching security-sensitive surfaces (auth, secrets, agent tools,
   audit logs), the change has been reviewed against `security-reviewer`'s
   checklist.
