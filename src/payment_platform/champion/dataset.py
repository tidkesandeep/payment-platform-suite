"""Synthetic (IEEE-CIS-shaped) labeled rows. Optional CSV overlay if present."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from payment_platform.champion.columns import FEATURE_NAMES


def ieee_cis_path() -> Path:
    repo = Path(__file__).resolve().parents[3]
    return repo / "data" / "ieee-cis" / "train_transaction.csv"


def synthetic_ieee_like(n: int = 8000, seed: int = 7) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Time-ordered samples. Label is behavioral fraud, not intent validity."""
    rng = np.random.default_rng(seed)
    timestamps = np.sort(rng.integers(1_700_000_000, 1_720_000_000, size=n).astype(np.float64))
    amount = rng.integers(200, 80_000, size=n).astype(np.float64)
    hour = rng.integers(0, 24, size=n).astype(np.float64)
    attempt_1h = rng.integers(1, 12, size=n).astype(np.float64)
    attempt_24h = attempt_1h + rng.integers(0, 20, size=n).astype(np.float64)
    approved_24h = rng.integers(0, 400_000, size=n).astype(np.float64)
    txn_30d = rng.integers(1, 40, size=n).astype(np.float64)
    avg_30d = rng.integers(500, 20_000, size=n).astype(np.float64)
    unique_merch = rng.integers(1, 15, size=n).astype(np.float64)
    days_since = rng.uniform(-1, 20, size=n)
    age_days = rng.uniform(0, 400, size=n)
    mer_avg = rng.integers(500, 25_000, size=n).astype(np.float64)
    mer_fraud = rng.uniform(0, 0.3, size=n)
    high_risk = rng.binomial(1, 0.08, size=n).astype(np.float64)
    home_match = rng.choice(np.array([-1.0, 0.0, 1.0]), size=n)
    new_device = rng.binomial(1, 0.25, size=n).astype(np.float64)
    device_customers = rng.integers(1, 8, size=n).astype(np.float64)
    intent_valid = rng.choice(np.array([-1.0, 0.0, 1.0]), size=n)
    agent = rng.binomial(1, 0.2, size=n).astype(np.float64)
    agent_txn = np.where(agent > 0, rng.integers(1, 30, size=n).astype(np.float64), -1.0)

    # Inject a fraud cluster so the model has a learnable pattern.
    fraud = (
        ((amount > 25_000) & (new_device > 0) & (attempt_1h >= 6))
        | ((high_risk > 0) & (amount > 8_000))
        | ((attempt_1h >= 9) & (mer_fraud > 0.12))
    ).astype(np.int32)
    flip = rng.random(n) < 0.03
    fraud = np.where(flip, 1 - fraud, fraud).astype(np.float64)

    columns = [
        amount,
        hour,
        attempt_1h,
        attempt_24h,
        approved_24h,
        txn_30d,
        avg_30d,
        unique_merch,
        days_since,
        age_days,
        mer_avg,
        mer_fraud,
        high_risk,
        home_match,
        new_device,
        device_customers,
        intent_valid,
        agent,
        agent_txn,
    ]
    x = np.column_stack(columns)
    assert x.shape[1] == len(FEATURE_NAMES)
    ieee = _try_ieee_cis(rng)
    if ieee is not None:
        x = np.vstack([x, ieee[0]])
        fraud = np.concatenate([fraud, ieee[1]])
        timestamps = np.concatenate([timestamps, ieee[2]])
        order = np.argsort(timestamps)
        x, fraud, timestamps = x[order], fraud[order], timestamps[order]
    return x, fraud, timestamps


def _try_ieee_cis(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    path = ieee_cis_path()
    if not path.is_file():
        return None
    try:
        import csv

        amounts: list[float] = []
        labels: list[float] = []
        times: list[float] = []
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for i, row in enumerate(reader):
                if i >= 20000:
                    break
                try:
                    amt = float(row.get("TransactionAmt") or 0) * 100.0
                    label = float(row.get("isFraud") or 0)
                    t = float(row.get("TransactionDT") or i)
                except ValueError:
                    continue
                amounts.append(amt)
                labels.append(label)
                times.append(t)
        if not amounts:
            return None
        n = len(amounts)
        x = np.zeros((n, len(FEATURE_NAMES)), dtype=np.float64)
        x[:, 0] = np.array(amounts)
        x[:, 1] = rng.integers(0, 24, size=n)
        x[:, 2] = 1.0
        x[:, 14] = rng.binomial(1, 0.2, size=n)
        return x, np.array(labels, dtype=np.float64), np.array(times, dtype=np.float64)
    except OSError:
        return None
