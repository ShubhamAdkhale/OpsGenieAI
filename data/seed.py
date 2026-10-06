"""Seed / re-seed the SQLite database (§12, §29).

    cd backend
    python ../data/seed.py            # create tables and seed if empty
    python ../data/seed.py --force    # wipe and rebuild from scratch

The real work lives in `backend/app/seeding.py` so that
`POST /api/simulation/reset` can call exactly the same code path — the demo
reset and the CLI seed can never diverge.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal, create_all  # noqa: E402
from app.models import Machine, Product, Shipment, Workflow  # noqa: E402
from app.seeding import reseed, seed_if_empty  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the OpsGenie AI database.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete every row and rebuild the baseline from seed_config.",
    )
    args = parser.parse_args()

    create_all()
    db = SessionLocal()
    try:
        if args.force:
            reseed(db)
            print("Database wiped and reseeded.")
        elif seed_if_empty(db):
            print("Database was empty — seeded the baseline.")
        else:
            print("Database already contains data. Use --force to rebuild.")

        print("\nRow counts:")
        for label, model in (
            ("products", Product),
            ("machines", Machine),
            ("shipments", Shipment),
            ("workflows", Workflow),
        ):
            print(f"  {label:<12} {db.query(model).count()}")

        hero = db.query(Shipment).filter(Shipment.is_hero.is_(True)).one_or_none()
        if hero is not None:
            print(
                f"\nHero shipment {hero.code}: Melt Index {hero.melt_index:.0f} "
                f"({hero.status}), expected loss Rs {hero.expected_loss_inr:,.0f}"
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
