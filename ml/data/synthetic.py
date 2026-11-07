"""Deterministic, seeded synthetic PaySim-shaped dataset for tests and for
local development when the real PaySim CSV isn't available. This is
explicitly labeled synthetic everywhere it's used — never presented as real
PaySim data or real measured performance.

Balances are simulated consistently account-by-account across increasing
`step` (not just random noise), so chronological feature tests (sender's
prior balance, prior transaction count, etc.) exercise real sequential
structure, matching what the real PaySim data looks like.
"""

import numpy as np
import pandas as pd

from ml.data.schema import VALID_TRANSACTION_TYPES

_DEBIT_LIKE_TYPES = {"CASH_OUT", "TRANSFER", "PAYMENT", "DEBIT"}  # reduce origin balance
_CREDIT_LIKE_TYPES = {"CASH_IN"}  # increase origin balance


def generate_synthetic_paysim(
    n_customers: int = 80,
    n_merchants: int = 15,
    n_steps: int = 500,
    txns_per_step: int = 10,
    fraud_rate: float = 0.05,
    seed: int = 42,
) -> pd.DataFrame:
    """Returns a DataFrame matching `ml.data.schema.RAW_COLUMNS` exactly,
    including `isFraud`/`isFlaggedFraud` (the caller is responsible for
    routing those to ground_truth only — this function just generates rows)."""
    rng = np.random.default_rng(seed)

    customers = [f"C{100000 + i}" for i in range(n_customers)]
    merchants = [f"M{900000 + i}" for i in range(n_merchants)]
    balances = {name: float(rng.uniform(1_000, 50_000)) for name in customers + merchants}

    rows: list[dict] = []
    txn_types = sorted(VALID_TRANSACTION_TYPES)

    for step in range(1, n_steps + 1):
        for _ in range(txns_per_step):
            txn_type = txn_types[rng.integers(0, len(txn_types))]
            origin = customers[rng.integers(0, len(customers))]

            if txn_type in ("PAYMENT", "TRANSFER"):
                dest_pool = merchants if txn_type == "PAYMENT" else customers
            else:
                dest_pool = [origin]  # CASH_IN/CASH_OUT/DEBIT act on the origin's own balance

            dest = dest_pool[rng.integers(0, len(dest_pool))]
            if dest == origin and len(dest_pool) > 1:
                dest = dest_pool[(dest_pool.index(dest) + 1) % len(dest_pool)]

            amount = round(float(rng.lognormal(mean=6.5, sigma=1.2)), 2)
            amount = min(amount, balances[origin] + 5_000)  # keep roughly plausible

            old_orig = balances[origin]
            old_dest = balances.get(dest, 0.0)

            if txn_type in _DEBIT_LIKE_TYPES:
                new_orig = max(old_orig - amount, 0.0)
            elif txn_type in _CREDIT_LIKE_TYPES:
                new_orig = old_orig + amount
            else:
                new_orig = old_orig

            if dest in merchants or txn_type in ("TRANSFER", "CASH_IN"):
                new_dest = old_dest + amount if dest != origin else old_dest
            else:
                new_dest = old_dest

            is_fraud = int(
                txn_type in ("TRANSFER", "CASH_OUT") and rng.random() < fraud_rate
            )
            is_flagged = int(is_fraud == 1 and rng.random() < 0.1)

            rows.append(
                {
                    "step": step,
                    "type": txn_type,
                    "amount": amount,
                    "nameOrig": origin,
                    "oldbalanceOrg": round(old_orig, 2),
                    "newbalanceOrig": round(new_orig, 2),
                    "nameDest": dest,
                    "oldbalanceDest": round(old_dest, 2),
                    "newbalanceDest": round(new_dest, 2),
                    "isFraud": is_fraud,
                    "isFlaggedFraud": is_flagged,
                }
            )

            balances[origin] = new_orig
            balances[dest] = new_dest

    df = pd.DataFrame(rows)
    return df.astype(
        {
            "step": "int64",
            "type": "object",
            "amount": "float64",
            "nameOrig": "object",
            "oldbalanceOrg": "float64",
            "newbalanceOrig": "float64",
            "nameDest": "object",
            "oldbalanceDest": "float64",
            "newbalanceDest": "float64",
            "isFraud": "int64",
            "isFlaggedFraud": "int64",
        }
    )
