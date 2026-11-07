#!/usr/bin/env python
"""Create or update a local demo user. Run from `backend/` with the venv
active, e.g.:

    python scripts/create_user.py --email admin@sentinelai.local \\
        --role admin --password <your-own-password>

There is no default/hardcoded password — CLAUDE.md and the Phase 5 brief
both require "no hardcoded production credentials"; this script always
requires `--password` on the command line (or `CREATE_USER_PASSWORD` in
the environment, so a password doesn't appear in shell history), hashes
it with the same `app.core.security.hash_password` the login path
verifies against, and never logs or prints it.
"""

import argparse
import os
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.user import USER_ROLES, User
from app.db.session import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--role", required=True, choices=USER_ROLES)
    parser.add_argument(
        "--password",
        default=os.environ.get("CREATE_USER_PASSWORD"),
        help="or set CREATE_USER_PASSWORD in the environment instead",
    )
    args = parser.parse_args()

    if not args.password:
        print("error: --password or CREATE_USER_PASSWORD is required", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == args.email))
        if user is None:
            user = User(
                email=args.email, role=args.role, password_hash=hash_password(args.password)
            )
            db.add(user)
            action = "created"
        else:
            user.role = args.role
            user.password_hash = hash_password(args.password)
            user.is_active = True
            action = "updated"
        db.commit()
        print(f"{action} user {args.email} ({args.role})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
