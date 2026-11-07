"""Run from backend/: python -m scripts.demo_data load|reset."""

import argparse
import json

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.demo.generator import DemoConfig
from app.demo.loader import load, reset
from app.ml.inference import load_active_artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Load/reset owned synthetic demonstration data")
    parser.add_argument("command", choices=["load", "reset"])
    parser.add_argument("--batch", default="showcase")
    parser.add_argument("--seed", type=int, default=75)
    parser.add_argument("--accounts", type=int, default=500)
    parser.add_argument("--transactions", type=int, default=10000)
    parser.add_argument("--days", type=int, default=65)
    parser.add_argument(
        "--confirm", default="", help='Reset only: exact phrase "DELETE DEMO <batch>"'
    )
    args = parser.parse_args()
    with SessionLocal() as db:
        try:
            if args.command == "reset":
                result = reset(db, args.batch, args.confirm)
            else:
                config = DemoConfig(
                    args.batch, args.seed, args.accounts, args.transactions, args.days
                )
                result = load(db, config, load_active_artifact(get_settings().ml_artifacts_dir))
        except ValueError as exc:
            db.rollback()
            parser.error(str(exc))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
