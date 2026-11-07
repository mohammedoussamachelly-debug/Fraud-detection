from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

# Naming convention keeps Alembic autogenerate diffs stable across SQLAlchemy
# versions once real tables are added (Phase 2).
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Default schema for ORM models is "app" — the operational schema. Anything in
# "ground_truth" (see docs/database-design.md §3) is deliberately never modeled
# here; the api_service role has no grant on it (backend/alembic baseline
# migration), so there would be nothing for such a model to query anyway.
metadata = MetaData(naming_convention=NAMING_CONVENTION, schema="app")
Base = declarative_base(metadata=metadata)
