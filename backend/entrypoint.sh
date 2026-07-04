#!/bin/sh
# Container entrypoint: bring the database schema to the latest Alembic
# revision, then start the API.
#
# This is safe in all three situations:
#   1. Brand-new empty database  -> migrations create everything.
#   2. Existing DB created before Alembic (has tables, no alembic_version)
#      -> we "stamp" it as the initial revision so Alembic knows the base
#         tables already exist, then apply only newer migrations.
#   3. DB already under Alembic   -> applies only pending migrations.
set -e

python - <<'PY'
from sqlalchemy import create_engine, inspect
from database import DATABASE_URL

engine = create_engine(DATABASE_URL)
insp = inspect(engine)
tables = insp.get_table_names()
has_version = "alembic_version" in tables
has_core = "site" in tables

import subprocess
if has_core and not has_version:
    # Pre-Alembic database with real data: mark it at the initial revision
    # WITHOUT re-running table creation, so existing data is untouched.
    print("Existing pre-Alembic database detected -> stamping initial revision")
    subprocess.run(["alembic", "stamp", "513d328c35a2"], check=True)

# Apply any migrations newer than the current stamp.
subprocess.run(["alembic", "upgrade", "head"], check=True)
PY

# Seed the province -> CRA-region mapping (and the Regional Manager / PSO
# Coordinator accounts). Idempotent: on an already-seeded database this only
# refreshes the mapping and creates nothing new. Required for the role
# dashboards to have any geographic scope to work with. New RM/Coordinator
# accounts print a one-time temporary password to these logs on first run.
python seed_provinces.py

exec uvicorn main:app --host 0.0.0.0 --port 8000
