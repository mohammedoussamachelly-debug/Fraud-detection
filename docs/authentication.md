# SentinelAI — Authentication (Phase 5, extended in Phase 6 Part A)

Status: **implemented and tested** against a real PostgreSQL database
(`backend/tests/test_auth.py`, plus role checks exercised throughout
`backend/tests/test_cases_api.py`, `test_alerts_api.py`, `test_audit_log.py`,
`test_ingestion.py`, `test_risk_score_api.py`, `test_graph_api.py`,
`test_accounts_transactions_api.py`, `test_investigations_api.py`).
Phase 6 Part A closed the one gap this document originally flagged: every
operational route (ingestion, scoring, graph, accounts/transactions) now
requires the same `service`/`analyst+` principals described below — see
"Known limitations" for exactly what changed.

## Principals

Per `docs/api-contracts.md` §0, there are four principals. Three are real
`app.users` rows; the fourth is a machine credential, never a user row:

| Principal | Backed by | Can do |
|---|---|---|
| `analyst` | `app.users` row, `role='analyst'` | Read accounts/transactions/graph data, view/list alerts and cases, create cases, update case status/priority/assignment, attach evidence, start/view/approve/reject/request-revision on investigations |
| `senior_analyst` | `app.users` row, `role='senior_analyst'` | Everything `analyst` can, **plus** record a case decision (`POST /cases/{id}/decision`) |
| `admin` | `app.users` row, `role='admin'` | Everything `senior_analyst` can, **plus** read the audit log (`GET /audit-log`) |
| `service` | **not** a user row — a static shared secret (`settings.service_api_key`) | `POST /risk-scores`, `POST /transactions/ingest`, `POST /risk/score` — the automated ingestion/scoring/alerting path. No case-decision rights, no user identity; actions it causes are audited with `user_id=null`. |

There is no `analyst < senior_analyst < admin` numeric hierarchy encoded
anywhere — each route declares the exact set of roles allowed
(`app/api/deps.py::require_role("analyst", "senior_analyst", "admin")`), so
"analyst+" in the docs always means "any of these three roles", not "role
value >= some threshold".

## How it works

- Passwords are hashed with `bcrypt` (`app/core/security.py::hash_password`/
  `verify_password`) — never stored or logged in plaintext.
- `POST /auth/login` (`app/api/routes/auth.py`) verifies the password and
  returns a signed JWT (`PyJWT`, HS256, `settings.jwt_secret_key`) carrying
  `sub` (user id) and `role`, expiring after
  `settings.access_token_expire_minutes` (default 30).
- Every protected route depends on `get_current_user`
  (`app/api/deps.py`), which decodes the JWT, loads the `User` row, and
  rejects a deactivated user (`is_active=false`) even if their token hasn't
  expired yet — a revoked account can't act on a still-valid token.
- `POST /risk-scores` depends on `require_service` instead, which compares
  the bearer token against `settings.service_api_key` with
  `secrets.compare_digest` (constant-time, not a plain `==`).
- Every login and every case/alert/evidence mutation writes an
  `app.audit_log_entries` row in the *same* database transaction as the
  action it describes (`app/services/audit.py`) — see
  `docs/alerts-and-cases.md` for exactly which actions are logged.

## Configuration

New environment variables (`infra/.env.example`, consumed by
`app/core/config.py::Settings`):

| Variable | Purpose | Dev default (never use in a real deployment) |
|---|---|---|
| `JWT_SECRET_KEY` | HS256 signing key for session tokens | `dev_jwt_secret_change_me` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session token lifetime | `30` |
| `SERVICE_API_KEY` | Shared secret for the `service` principal | `dev_service_api_key_change_me` |

Generate real values for a non-throwaway environment with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Creating users

There is **no seeded/default user and no hardcoded password** anywhere in
this codebase, per CLAUDE.md's "no hardcoded production credentials" rule.
Create one with the provided script, from `backend/` with the venv active
and `DATABASE_URL` pointing at a reachable Postgres:

```bash
python scripts/create_user.py --email admin@sentinelai.local --role admin --password 'choose-your-own'
```

`--password` is required (or set `CREATE_USER_PASSWORD` in the environment
instead, so it never appears in shell history); the script hashes it with
the same `app.core.security.hash_password` the login path verifies
against and never prints or logs it. Re-running the script for an
existing email updates that user's role/password and reactivates the
account (`is_active=true`).

## Example

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "admin@sentinelai.local", "password": "choose-your-own"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8001/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8001/api/v1/cases -H "Authorization: Bearer $TOKEN"
```

## Known limitations

- **No refresh tokens, no logout/revocation list.** `docs/api-contracts.md`
  §1 originally sketched `/auth/refresh` and `/auth/logout`; neither is
  implemented — a session is just a stateless JWT that's valid until it
  expires (30 minutes by default) or the user is deactivated. For a
  30-minute-lifetime local demo this is an accepted tradeoff, not an
  oversight; revocation-before-expiry would need a server-side session/
  deny-list table this phase didn't add.
- ~~Pre-existing Phase 1–4 routes remain unauthenticated~~ — **closed in
  Phase 6 Part A.** `POST /transactions/ingest` and `POST /risk/score`
  now require the `service` credential; `GET /accounts`,
  `GET /transactions`, and all four `/graph/*` routes now require
  `analyst`/`senior_analyst`/`admin`. Every pre-existing test for these
  routes was updated to authenticate (`tests/test_ingestion.py`, `tests/
  test_risk_score_api.py`, `tests/test_graph_api.py`,
  `tests/test_graph_build.py`, `tests/test_graph_fund_flow.py`,
  `tests/test_graph_performance.py`,
  `tests/test_accounts_transactions_api.py`), plus new tests asserting
  the unauthenticated/wrong-principal paths are rejected. No route lets
  a client choose its own role: the only role-bearing input is the JWT
  issued by `POST /auth/login`, itself derived from the `users.role`
  column — never a request parameter or header a caller can set.
- **No password reset / account-recovery flow** — `scripts/create_user.py`
  (run again for the same email) is the only way to change a password.
