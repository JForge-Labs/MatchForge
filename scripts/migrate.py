"""Bring the database to the current Alembic head.

Safe to run on every boot (docker-entrypoint.sh):
- Fresh/empty DB (no app tables yet): skip — init_db.py creates the schema
  and stamps head itself.
- Existing pre-Alembic DB: stamp the baseline, then upgrade to head.
- Already-stamped DB: plain upgrade to head (no-op when current).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings

BASELINE = "0001_baseline"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))

    engine = create_engine(get_settings().database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    engine.dispose()

    if "profiles" not in tables:
        print("No app tables yet — run scripts/init_db.py first; skipping migrate.")
        return
    if "alembic_version" not in tables:
        print(f"Pre-Alembic database detected — stamping {BASELINE}.")
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")
    print("Database is at Alembic head.")


if __name__ == "__main__":
    main()
