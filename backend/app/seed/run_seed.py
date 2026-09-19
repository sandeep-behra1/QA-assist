"""Seed CLI:  python -m app.seed.run_seed [--reset]"""

from __future__ import annotations

import argparse
import sys

from app.db.session import SessionLocal
from app.seed.seed_data import seed_all


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the CIMET QA Gate database.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing rows before seeding (destroys scoring history).",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        result = seed_all(db, reset=args.reset)

    if result["status"] == "already_seeded":
        print("Database already contains data. Re-run with --reset to reseed.")
        return 0

    print(
        "Seeded: "
        + ", ".join(f"{key}={value}" for key, value in result.items() if key != "status")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
