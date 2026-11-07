# Synthetic demonstration data

The demo command writes only to the existing operational PostgreSQL database. It does not train a model, load ground-truth labels, import the full PaySim dataset, build images, or touch Docker volumes.

## Load

Use the existing `backend/.venv`, running PostgreSQL container, and `backend/.env`. Apply migrations with the existing administrator connection (see README); the application connection cannot perform schema migrations:

```sh
cd backend
# ALEMBIC_DATABASE_URL must contain your existing migration administrator URL.
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.demo_data load
```

Defaults: batch `showcase`, seed `75`, 500 accounts, 10,000 transactions, 65 simulated days. Example smaller isolated batch:

```sh
.venv/bin/python -m scripts.demo_data load --batch training-session --seed 75 --accounts 50 --transactions 300 --days 60
```

Accounts must number 50–5,000; days 60–365; transaction count must cover scenario history (`accounts + days * 2 + 100` minimum) and cannot exceed 100,000. The upper bound is a validation limit, not a performance guarantee. The default load can take several minutes because every transaction receives a genuine SHAP explanation.

The generator uses deterministic UUIDs and references prefixed `CDEMO:`, `MDEMO:` and `DEMO:`. All records belong to `app.demo_batches` and `app.demo_records`. Repeating an identical configuration returns the existing batch without adding rows. A different configuration under the same name is rejected. The saved artifact version is recorded with each score; loading an existing batch does not silently rescore it after a model change.

Rows are inserted in batches in one transaction. Model features use the production `get_sender_history` query and shared `engineer_features` transformation; history excludes the event and every other transaction in its simulation hour. Inference uses the active frozen XGBoost pipeline. Batched SHAP uses that artifact's background sample, explainer, and production feature grouping. Failure rolls back the complete batch.

## Reset

```sh
.venv/bin/python -m scripts.demo_data reset --batch showcase --confirm 'DELETE DEMO showcase'
```

The exact confirmation is mandatory. Reset removes only ledger-owned accounts, transactions, scores, alerts, prepared/created demo cases and those cases' dependent evidence, reports and decisions. It retains append-only audit records and user accounts. Reset refuses mixed case links, unowned scores/alerts/transactions, external evidence references, or active investigation runs. It takes short database write locks during reference checks and deletion, so concurrent writers cannot bypass the ownership checks. Reads remain available. A missing batch is a no-op.

Do not work around a refused reset by deleting tables or volumes. Keep the batch when other investigations depend on it. Reset and regenerate only when you intend to discard that batch's investigation work.

## Data and model limitations

- Activity is synthetic, denominated in synthetic units, and begins at the existing PaySim simulation epoch (2026-01-01 UTC). No real customer names or financial records are used.
- Opening balances are an explicit 2,000,000 units per account. Every transfer updates both balances exactly in cents; money is conserved and balances stay nonnegative. This is a controlled demonstration ledger, not a reconstruction of external banking cash flows. CASH_IN/CASH_OUT are payment-type labels on these synthetic account-to-account movements.
- Ordinary accounts repeatedly interact within small counterparty groups. Special scenario accounts are separated so their histories and connections are understandable.
- Designed scenarios are structural examples, not ground-truth fraud labels. Model-threshold alerts use the actual saved threshold. Eight additional `demo_rule_*` alerts explicitly identify controlled scenario rules.
- The PaySim model is not calibrated for this new distribution. The verified default batch produced **zero model-threshold alerts**. This result is preserved. No scores or explanations were changed to make a scenario look risky.
- Migration 0008 expands score/threshold precision to 15 decimal places, preserving very small probabilities. Previously rounded unrelated records cannot regain precision automatically. The default demo was regenerated after this migration.
- Generated accounts include a small number of unused reserve accounts. Graph queries remain bounded and disclose truncation; connectedness alone does not establish wrongdoing.

See [scenario descriptions](demo-scenarios.md), [walkthrough](demo-walkthrough.md), and [verification](frontend-qa.md).
