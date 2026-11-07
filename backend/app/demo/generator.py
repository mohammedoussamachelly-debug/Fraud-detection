"""Pure deterministic transaction plan; scenario intent never sets a model score."""

import random
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.services.ingestion import PAYSIM_EPOCH, _occurred_at_for_step

NAMESPACE = uuid.UUID("fcbd40f1-e773-42ab-9653-156a40ca2399")


@dataclass(frozen=True)
class DemoConfig:
    batch: str = "showcase"
    seed: int = 75
    accounts: int = 500
    transactions: int = 10_000
    days: int = 65

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", self.batch):
            raise ValueError("Batch must be a lowercase name of 1–40 letters, digits or hyphens")
        if not 50 <= self.accounts <= 5000:
            raise ValueError("Choose 50–5000 accounts")
        if not 60 <= self.days <= 365:
            raise ValueError("Choose 60–365 simulated days")
        if not self.accounts + self.days * 2 + 100 <= self.transactions <= 100_000:
            raise ValueError(
                "Transaction count must cover accounts, scenario history, and patterns"
            )


def record_id(batch: str, kind: str, key: object) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{batch}/{kind}/{key}")


def generate(config: DemoConfig) -> tuple[list[dict], list[dict], list[dict]]:
    config.validate()
    rng = random.Random(config.seed)
    labels = {
        0: "Everyday customer",
        1: "Growing business",
        12: "Collection account",
        19: "Connected business A",
        20: "Connected business B",
        21: "Connected business C",
        22: "Connected business D",
        30: "Local shop",
        31: "Utility merchant",
        32: "Equipment supplier",
    }
    accounts = [
        dict(
            id=record_id(config.batch, "account", i),
            external_ref=(
                f"{'M' if i in (30,31,32) else 'C'}DEMO:{config.batch}:"
                f"{labels.get(i, f'Customer {i + 1:03}')}"
            ),
            account_type="merchant" if i in (30, 31, 32) else "customer",
            first_seen_at=PAYSIM_EPOCH,
        )
        for i in range(config.accounts)
    ]
    # step, origin index, recipient index, amount in cents, type, scenario
    plan: list[tuple[int, int, int, int, str, str | None]] = []
    for day in range(config.days):
        plan.append((day * 24 + 10, 0, 30 + day % 2, rng.randint(800, 18000), "PAYMENT", "normal"))
        if day < config.days - 2:
            plan.append((day * 24 + 14, 1, 32, rng.randint(15000, 45000), "TRANSFER", None))
    late = (config.days - 2) * 24
    plan.append((late + 12, 1, 32, 9_000_000, "TRANSFER", "unusual"))
    for i in range(2, 12):
        plan.append((late, i, 12, (i + 1) * 100_000, "TRANSFER", "incoming"))
    for i in range(13, 19):
        plan.append((late + 1, 12, i, 700_000, "TRANSFER", "redistribution"))
    for i, (origin, dest) in enumerate(((19, 20), (20, 21), (21, 22), (22, 19), (19, 21))):
        plan.append((late + 2 + i, origin, dest, 4_500_000 - i * 100_000, "TRANSFER", "linked"))
    # Ensure every remaining account appears; background activity stays in small
    # repeat-counterparty clusters instead of producing a decorative random hairball.
    for i in range(40, config.accounts):
        plan.append(
            (
                i % (config.days * 24),
                i,
                40 + (i - 39) % (config.accounts - 40),
                2500,
                "TRANSFER",
                None,
            )
        )
    while len(plan) < config.transactions:
        origin = rng.randrange(40, config.accounts)
        group_start = 40 + ((origin - 40) // 12) * 12
        peers = [
            i for i in range(group_start, min(group_start + 12, config.accounts)) if i != origin
        ]
        dest = rng.choice(peers or [40 if origin != 40 else 41])
        kind = rng.choices(
            ["PAYMENT", "TRANSFER", "DEBIT", "CASH_IN", "CASH_OUT"], [45, 30, 8, 9, 8]
        )[0]
        amount = max(100, round(rng.lognormvariate(8.5, 1.2)))
        plan.append((rng.randrange(config.days * 24), origin, dest, amount, kind, None))
    plan.sort(key=lambda item: item[0])  # stable tie order; history excludes same-step rows
    balances = [200_000_000] * config.accounts  # explicit synthetic opening balances
    transactions = []
    scenario_ids: dict[str, list[str]] = {
        key: [] for key in ("normal", "unusual", "incoming", "redistribution", "linked")
    }
    for index, (step, origin, dest, proposed, kind, scenario) in enumerate(plan):
        cents = min(proposed, balances[origin])
        before_origin, before_dest = balances[origin], balances[dest]
        balances[origin] -= cents
        balances[dest] += cents
        tx_id = record_id(config.batch, "transaction", index)
        transactions.append(
            dict(
                id=tx_id,
                external_ref=f"DEMO:{config.batch}:Transfer {index + 1:05}",
                step=step,
                occurred_at=_occurred_at_for_step(step),
                type=kind,
                amount=Decimal(cents) / 100,
                origin_account_id=accounts[origin]["id"],
                dest_account_id=accounts[dest]["id"],
                origin_balance_before=Decimal(before_origin) / 100,
                origin_balance_after=Decimal(balances[origin]) / 100,
                dest_balance_before=Decimal(before_dest) / 100,
                dest_balance_after=Decimal(balances[dest]) / 100,
            )
        )
        if scenario:
            scenario_ids[scenario].append(str(tx_id))
    metadata = [
        (
            "normal",
            "Everyday payments",
            (
                "A customer makes regular payments over time. Inspect the actual model "
                "prediction; ordinary behavior does not guarantee a low score."
            ),
            0,
        ),
        (
            "unusual",
            "A larger-than-usual transfer",
            (
                "A business normally sends modest transfers, then makes a much larger "
                "payment. Compare it with its earlier activity."
            ),
            1,
        ),
        (
            "incoming",
            "Many senders, one recipient",
            (
                "Ten customers send funds to one collection account. Explore who participated "
                "and the recorded transfer amounts."
            ),
            12,
        ),
        (
            "redistribution",
            "Funds move on quickly",
            (
                "The collection account sends funds to six recipients one simulation hour "
                "after receiving multiple transfers."
            ),
            12,
        ),
        (
            "linked",
            "Connected transfer activity",
            (
                "Four accounts make a sequence of connected transfers, including a return "
                "path. Review the supporting evidence together."
            ),
            19,
        ),
    ]
    scenarios = [
        dict(
            key=key,
            title=title,
            description=description,
            account_id=str(accounts[account]["id"]),
            transaction_ids=scenario_ids[key],
            transaction_id=scenario_ids[key][-1],
            synthetic=True,
        )
        for key, title, description, account in metadata
    ]
    return accounts, transactions, scenarios
