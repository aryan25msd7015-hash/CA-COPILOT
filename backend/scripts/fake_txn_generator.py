"""Generate fake banking transactions for load and model testing."""

from __future__ import annotations

import argparse
import csv
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path


def generate_rows(count: int, seed: int) -> list[dict[str, object]]:
    rng = random.Random(seed)
    start = datetime.now(UTC) - timedelta(days=180)
    rows: list[dict[str, object]] = []
    for idx in range(count):
        ts = start + timedelta(minutes=rng.randint(0, 180 * 24 * 60))
        amount = round(rng.uniform(500.0, 2500000.0), 2)
        is_new_bene = rng.random() < 0.22
        is_international = rng.random() < 0.08
        pan_mismatch = rng.random() < 0.05
        rows.append(
            {
                "txn_id": f"txn-{idx:07d}",
                "account_id": f"ACC-{rng.randint(100000, 999999)}",
                "amount": amount,
                "timestamp": ts.isoformat(),
                "txn_count_24h": rng.randint(1, 9),
                "total_amount_24h": round(amount + rng.uniform(0.0, 4000000.0), 2),
                "is_new_beneficiary": is_new_bene,
                "is_international": is_international,
                "pan_gstin_mismatch": pan_mismatch,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate fake bank transactions.")
    parser.add_argument("--count", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("backend/data/fake_txns_100k.csv"),
    )
    args = parser.parse_args()
    rows = generate_rows(count=args.count, seed=args.seed)
    write_csv(args.output, rows)
    print(f"generated={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()
