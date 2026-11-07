# A five-minute investigation

## Launch without rebuilding Docker

Keep the existing PostgreSQL container running. Use the existing virtual environment and Node installation. Apply migrations and load the demo as described in [demo-data.md](demo-data.md).

In one terminal:

```sh
cd backend
CORS_ORIGINS=http://localhost:5174 .venv/bin/uvicorn app.main:app --reload --port 8001
```

In another:

```sh
cd frontend
VITE_API_BASE_URL=http://localhost:8001/api/v1 npm run dev -- --port 5174 --strictPort
```

Open **http://localhost:5174**. If those servers are already running, reuse them after checking the backend's `CORS_ORIGINS`. `localhost` and `127.0.0.1` are different browser origins. Choose another pair of free ports if necessary and update both environment variables. No Docker build is needed.

## Sign in

The requested account is a **SentinelAI application user**, not your PostgreSQL, Google, or OpenAI account. There is no built-in password. Use an existing user, or create your own from `backend/` without placing its password in shell history:

```sh
.venv/bin/python - <<'PY'
import getpass, os, subprocess, sys
email = input('SentinelAI email: ')
os.environ['CREATE_USER_PASSWORD'] = getpass.getpass('Choose a password: ')
subprocess.run([sys.executable, '-m', 'scripts.create_user', '--email', email,
                '--role', 'senior_analyst'], check=True)
PY
```

Use that email/password on the sign-in form. Choose `analyst` for a user who can investigate/review reports but cannot resolve cases; choose `senior_analyst` for the full demonstration. Audit-log access requires `admin`. Creating an existing email updates that user's password and role.

## Walk through the product

1. **Dashboard:** see actual stored counts and the prioritized alert queue. Expand **Explore demo** and choose **Connected transfer activity**.
2. **Explore scenario:** review the named accounts, amount, actual model score and risk factors. The current demo's low scores are expected observations, not a promise about future data.
3. **Open investigation:** the prepared linked-activity case already contains five payments. Choose a payment from the dropdown; its history, factors and connections remain in the same workspace.
4. **Supporting evidence:** inspect the transaction snapshots, save connected accounts/history and add an analyst note. Raw IDs and JSON are inside **Technical details**.
5. **Start AI investigation:** progress and the resulting report appear inline. When `LLM_PROVIDER=mock`, the report prominently says **Mock AI report**. Anthropic runs display their actual provider instead. It uses deterministic demonstration text with database-backed evidence; it is not live LLM reasoning. The XGBoost assessments remain genuine, independently of the mock report provider.
6. **Review investigation report:** inspect findings, uncertainties and source citations. Approve, reject or request a revision. Reopening the case or repeating Start reuses the existing report. A failed report remains visible; the advanced existing run API supports an explicit new run if needed.
7. **Case decision:** a senior analyst/admin separately chooses a decision, writes a rationale and confirms. This action resolves the case. Approving the AI report alone never resolves it.

Use **Transactions** to search account/payment references and filter by type. Account-history links apply the account filter automatically. **Advanced / Admin** retains account profiles, network tooling, case administration and the administrator audit log.

All demo records remain synthetic. After a session, an intentional batch reset also removes that batch's investigation work while retaining audit history. Live QA creates an isolated temporary batch and login, removes the batch after verification, and deactivates the login while preserving audit history. It does not create a shared default password.
