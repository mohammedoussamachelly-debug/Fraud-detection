# SentinelAI — Feature Engineering

Status: **implemented**, matching `backend/app/ml/features.py` exactly. This
document describes what that module actually does — if the two ever
disagree, the code is correct and this doc is stale.

## 1. The shared transformation

Both the offline training pipeline (`ml/training/`) and the live inference
path (`backend/app/services/risk_scoring.py`) call the same function,
`engineer_features` (vectorized, bulk) / `build_feature_row` (single-row
wrapper around it), in `backend/app/ml/features.py`. This is the literal
mechanism behind "training and inference use identical transformations" —
not a convention both sides happen to follow, but one function both sides
import and call.

What legitimately differs between the two paths is only **how the
historical aggregate inputs are computed**, because the two run in very
different contexts:

| | Training | Inference |
|---|---|---|
| Input | Full PaySim DataFrame, all steps at once | One transaction at a time |
| Mechanism | Bulk, vectorized pandas (`ml/training/historical_features.py`) | One SQL query (`backend/app/services/history.py`) |
| Data source | The CSV/synthetic DataFrame being trained on | `app.transactions` (already-ingested rows) |

Both are verified to agree on the same scenario by
`backend/tests/test_feature_consistency.py` — the project's "inference
consistency" test.

## 2. Feature list

| Feature | Type | Definition |
|---|---|---|
| `amount` | numeric | Transaction amount, as given |
| `log_amount` | numeric | `log1p(amount)` — amounts are heavily right-skewed |
| `hour_of_day` | numeric | `step % 24` — PaySim's `step` is an hour-wide bucket; see §4 |
| `sender_prev_balance` | numeric | Sender's balance *immediately before* this transaction (PaySim `oldbalanceOrg`) — provided directly, never looked up |
| `recipient_prev_balance` | numeric | Same, for the recipient (`oldbalanceDest`) |
| `num_prev_txns_by_sender` | numeric | Count of the sender's transactions with a strictly earlier `step` |
| `historical_avg_amount` | numeric | Mean amount of those prior transactions |
| `num_unique_prev_recipients` | numeric | Distinct recipients among those prior transactions |
| `recent_txn_frequency` | numeric | Count of the sender's prior transactions within the last `RECENT_TXN_WINDOW_STEPS` (24) steps |
| `sender_is_new` | numeric (0/1) | See §3 |
| `transaction_type` | categorical | One of `CASH_IN`, `CASH_OUT`, `DEBIT`, `PAYMENT`, `TRANSFER` — one-hot encoded during training |

**Never used, by design** (`FORBIDDEN_FEATURE_COLUMNS`, asserted against in
`ml/tests/test_leakage.py`): `isFraud`, `isFlaggedFraud` (ground truth — see
`docs/database-design.md` §3), and `newbalanceOrig`/`newbalanceDest`
(post-transaction balances — using them to score the transaction that
produced them would be scoring with the outcome already known).

## 3. New-account / first-transaction policy

An account's first-ever transaction as a sender has no history. Rather than
imputing a plausible-looking value, every historical aggregate is set to
its zero/empty value **and** an explicit `sender_is_new` indicator is set —
so the model can distinguish "genuinely no history" from "one prior
transaction that happened to be small," which a bare zero can't do on its
own (`new_account_history_defaults()` in `features.py`). The same applies
to an account `app/services/history.py` has never seen in `app.accounts`
at all — it gets the identical defaults, never a fabricated value.

## 4. Chronological-ordering assumption

PaySim's `step` is an hour-wide bucket — many transactions can share the
same `step`, and the CSV's row order within a step carries no reliable
meaning. Every historical aggregate therefore uses a **strict** `step <
current_step` filter, never `<=`: transactions sharing a step with the one
being scored are treated as simultaneous and excluded from each other's
history, regardless of which one appears first in the source file. This is
what prevents a row-ordering artifact in the raw data from leaking
information (see the hand-constructed same-step test case in
`ml/tests/test_historical_features.py`).

## 5. Why accuracy alone is insufficient

PaySim's fraud rate is well under 1%. A classifier that predicts
"legitimate" for every transaction scores >99% accuracy while catching zero
fraud — accuracy is dominated by the majority class and says nothing about
the thing this system actually needs to detect. See
`docs/model-evaluation.md` for the metrics actually used instead
(precision/recall/F1/PR-AUC/false-alert rate) and why.
