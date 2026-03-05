"""
setup_supabase.py
=================
Creates all KeySentinel tables on the Supabase PostgreSQL database
using credentials from the .env file at the project root.

Requirements
------------
Install the psycopg2 driver once:
    uv add psycopg2-binary

Usage
-----
    uv run scripts/setup_supabase.py
"""

import pathlib
import sys


# ── Load .env manually (no extra dependency) ──────────────────────────
def _load_env(env_path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not env_path.exists():
        print(f"[setup_supabase] .env not found at {env_path}", file=sys.stderr)
        return env
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


ROOT = pathlib.Path(__file__).resolve().parent.parent
env = _load_env(ROOT / ".env")

DB_USER = env.get("DB_USER")
DB_PASSWORD = env.get("DB_PASSWORD")
DB_HOST = env.get("DB_HOST")
DB_PORT = env.get("DB_PORT", "5432")
DB_NAME = env.get("DB_NAME", "postgres")

if not all([DB_USER, DB_PASSWORD, DB_HOST]):
    print(
        "[setup_supabase] Missing DB_USER / DB_PASSWORD / DB_HOST in .env",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Build PostgreSQL URL ───────────────────────────────────────────────
# psycopg2 requires the password to be URL-encoded if it contains special chars
from urllib.parse import quote_plus

DB_URL = (
    f"postgresql+psycopg2://{quote_plus(DB_USER)}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ── Create tables via SQLAlchemy ORM models ────────────────────────────
# Add project root to sys.path so app.models can be imported
sys.path.insert(0, str(ROOT))

try:
    from sqlalchemy import create_engine, text
    from app.models.schema import Base
except ImportError as exc:
    print(f"[setup_supabase] Import error: {exc}", file=sys.stderr)
    sys.exit(1)

print(f"[setup_supabase] Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME} …")

try:
    engine = create_engine(DB_URL, echo=False)

    # PostgreSQL needs the enum type created before the tables
    with engine.connect() as conn:
        conn.execute(
            text(
                """
            DO $$ BEGIN
                CREATE TYPE activitycategory AS ENUM ('coding', 'writing', 'gaming');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
        """
            )
        )
        conn.commit()

    # Create all tables defined in the ORM
    Base.metadata.create_all(engine)
    print("[setup_supabase] ✓ All tables created successfully.")

except Exception as exc:
    print(f"[setup_supabase] ✗ Failed: {exc}", file=sys.stderr)
    sys.exit(1)
