"""Live browser verification with disposable, owned synthetic records and login.

Run from backend/: .venv/bin/python -m scripts.verify_demo
Reuse the running API, Vite and Chromium CDP endpoint; never rebuild containers.
"""

import json
import os
import secrets
import subprocess
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.models import User
from app.db.session import SessionLocal
from app.demo.generator import DemoConfig
from app.demo.loader import load, reset
from app.ml.inference import load_active_artifact


def main() -> None:
    config = DemoConfig(
        batch="browser-qa-" + uuid.uuid4().hex[:12], accounts=50, transactions=300, days=60
    )
    password = secrets.token_urlsafe(32)
    user_id = None
    root = Path(__file__).resolve().parents[2]
    try:
        with SessionLocal() as db:
            result = load(db, config, load_active_artifact(get_settings().ml_artifacts_dir))
            assert result["created"]
            user = User(
                email=f"{config.batch}@sentinelai.test",
                password_hash=hash_password(password),
                role="senior_analyst",
                is_active=True,
            )
            db.add(user)
            db.commit()
            user_id = user.id
            email = user.email
        # Owner-only directory and file; credentials never enter argv or logs.
        with TemporaryDirectory(prefix="sentinel-browser-qa-") as directory:
            credentials = Path(directory) / "credentials.json"
            credentials.touch(mode=0o600)
            credentials.write_text(json.dumps({"email": email, "password": password}))
            env = {
                **os.environ,
                "QA_CREDENTIALS_FILE": str(credentials),
                "QA_BATCH": config.batch,
            }
            subprocess.run(
                ["node", "qa/live-demo-check.mjs"], cwd=root / "frontend", env=env, check=True
            )
    finally:
        with SessionLocal() as db:
            if user_id is not None:
                user = db.get(User, user_id)
                assert user is not None
                user.is_active = False
                db.commit()
            # Only this invocation's random namespace can be removed. The normal
            # ownership/active-run guards apply, even if browser verification fails.
            reset(db, config.batch, f"DELETE DEMO {config.batch}")
        print("Removed temporary QA batch; deactivated QA login; retained audit history.")


if __name__ == "__main__":
    main()
