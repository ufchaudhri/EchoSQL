"""
EchoSQL Database Seeding Script
================================
Generates realistic banking data for: customers, accounts, transactions.

Features:
  - Idempotent: truncates seeded tables and resets sequences on every run
  - FK-safe: fetches the actual inserted ID list from each table before referencing
    it in child tables — never guesses IDs with randint(1, count)
  - Preserves static data: branches, transaction_types, schema_context are not touched
  - Loads DATABASE_URL from backend/.env automatically

Usage (from the project root or backend/ directory):
    cd backend
    venv\\Scripts\\activate
    python database/seed_data.py

Env overrides:
    DATABASE_URL          (preferred, loaded from .env)
    DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD  (fallback)
    TOTAL_CUSTOMERS       (default 100 000)
    TOTAL_ACCOUNTS        (default  50 000)
    TOTAL_TRANSACTIONS    (default 200 000)
"""

import os
import re
import sys
import time
import uuid
import random
from pathlib import Path

# Windows cp1252 consoles can't print checkmarks / emoji — force UTF-8 output.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import psycopg
from psycopg import sql
from faker import Faker
from tqdm import tqdm


# ── Load .env ────────────────────────────────────────────────────────────────────
def _load_env(path: Path) -> None:
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)
    except FileNotFoundError:
        pass


# Try backend/.env relative to this file's location
_load_env(Path(__file__).resolve().parent.parent / ".env")


# ── Connection settings ──────────────────────────────────────────────────────────
_url = os.getenv("DATABASE_URL", "")
_m = re.match(r"postgresql://([^:]+):([^@]*)@([^:/]+):(\d+)/(.+)", _url) if _url else None
if _m:
    DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME = _m.groups()
else:
    DB_USER     = os.getenv("DB_USER",     "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST     = os.getenv("DB_HOST",     "localhost")
    DB_PORT     = os.getenv("DB_PORT",     "5432")
    DB_NAME     = os.getenv("DB_NAME",     "echosql")

BATCH_SIZE         = 10_000
TOTAL_CUSTOMERS    = int(os.getenv("TOTAL_CUSTOMERS",    "100000"))
TOTAL_ACCOUNTS     = int(os.getenv("TOTAL_ACCOUNTS",      "50000"))
TOTAL_TRANSACTIONS = int(os.getenv("TOTAL_TRANSACTIONS", "200000"))

fake = Faker()
Faker.seed(42)
random.seed(42)


# ── DB helpers ───────────────────────────────────────────────────────────────────
def connect() -> psycopg.Connection:
    try:
        return psycopg.connect(
            host=DB_HOST, port=DB_PORT,
            dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD,
            autocommit=False,
        )
    except Exception as exc:
        print(f"✗ Cannot connect to PostgreSQL: {exc}")
        print(f"  Check DATABASE_URL in backend/.env")
        raise


def fetch_ids(conn: psycopg.Connection, table: str, id_col: str) -> list[int]:
    """Return every primary-key value in a table as a plain Python list."""
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT {} FROM {}").format(
                sql.Identifier(id_col),
                sql.Identifier(table),
            )
        )
        return [row[0] for row in cur.fetchall()]


def count_rows(conn: psycopg.Connection, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(table))
        )
        return cur.fetchone()[0]


# ── Step 0: truncate seeded tables ───────────────────────────────────────────────
def truncate_seeded_tables(conn: psycopg.Connection) -> None:
    """
    Drop all previously seeded rows and reset the auto-increment sequences so
    re-running the script always produces a clean, consistent dataset.

    Static/reference tables are intentionally excluded:
      branches, transaction_types, schema_context
    """
    print("\n🗑  Clearing seeded tables (TRUNCATE + RESTART IDENTITY)...")
    with conn.cursor() as cur:
        # Truncate in child-first order; CASCADE handles any remaining FK deps.
        cur.execute(
            "TRUNCATE TABLE transactions, accounts, customers, query_cache "
            "RESTART IDENTITY CASCADE"
        )
    conn.commit()
    print("  ✓ Done")


# ── Step 1: customers ─────────────────────────────────────────────────────────────
def seed_customers(conn: psycopg.Connection) -> list[int]:
    """
    Insert TOTAL_CUSTOMERS rows and return the actual customer_id list.
    Emails are generated as <username>_<global_index>@<domain> to guarantee
    uniqueness without relying on Faker's exhaustible .unique pool.
    """
    print(f"\n📝 Seeding {TOTAL_CUSTOMERS:,} customers...")

    account_types = ["Savings", "Checking", "Premium", "Business"]
    kyc_statuses  = ["Verified", "Pending", "Rejected"]

    with conn.cursor() as cur:
        for start in tqdm(range(0, TOTAL_CUSTOMERS, BATCH_SIZE)):
            end = min(start + BATCH_SIZE, TOTAL_CUSTOMERS)
            rows = [
                (
                    fake.name(),
                    f"{fake.user_name()}_{start + i}@{fake.free_email_domain()}",
                    fake.phone_number()[:20],
                    random.choice(account_types),
                    random.choice(kyc_statuses),
                    fake.date_time_between(start_date="-2y", end_date="now"),
                )
                for i in range(end - start)
            ]
            cur.executemany(
                """
                INSERT INTO customers (name, email, phone, account_type, kyc_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                """,
                rows,
            )
            conn.commit()

    ids = fetch_ids(conn, "customers", "customer_id")
    print(f"  ✓ {len(ids):,} customers")
    return ids


# ── Step 2: accounts ──────────────────────────────────────────────────────────────
def seed_accounts(
    conn: psycopg.Connection,
    customer_ids: list[int],
    branch_ids: list[int],
) -> list[int]:
    """
    Insert TOTAL_ACCOUNTS rows.
    customer_ids and branch_ids come from fetch_ids() — every value is
    guaranteed to exist in its parent table.
    Account numbers use UUID4 substrings to avoid any uniqueness exhaustion.
    """
    print(f"\n📝 Seeding {TOTAL_ACCOUNTS:,} accounts...")

    account_types = ["Savings", "Checking", "Premium", "Business"]
    statuses      = ["Active", "Inactive", "Frozen"]

    with conn.cursor() as cur:
        for start in tqdm(range(0, TOTAL_ACCOUNTS, BATCH_SIZE)):
            end = min(start + BATCH_SIZE, TOTAL_ACCOUNTS)
            rows = [
                (
                    random.choice(customer_ids),
                    random.choice(branch_ids),
                    uuid.uuid4().hex[:20].upper(),   # unique, no exhaustion
                    random.choice(account_types),
                    round(random.uniform(100, 1_000_000), 2),
                    random.choice(statuses),
                    fake.date_time_between(start_date="-2y", end_date="now"),
                )
                for _ in range(end - start)
            ]
            cur.executemany(
                """
                INSERT INTO accounts
                  (customer_id, branch_id, account_number, account_type, balance, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (account_number) DO NOTHING
                """,
                rows,
            )
            conn.commit()

    ids = fetch_ids(conn, "accounts", "account_id")
    print(f"  ✓ {len(ids):,} accounts")
    return ids


# ── Step 3: transactions ──────────────────────────────────────────────────────────
def seed_transactions(
    conn: psycopg.Connection,
    account_ids: list[int],
    type_ids: list[int],
) -> None:
    """
    Insert TOTAL_TRANSACTIONS rows.
    account_ids and type_ids are real IDs fetched from the DB — no FK risk.
    """
    print(f"\n📝 Seeding {TOTAL_TRANSACTIONS:,} transactions...")

    statuses = ["Completed", "Pending", "Failed"]

    with conn.cursor() as cur:
        for start in tqdm(range(0, TOTAL_TRANSACTIONS, BATCH_SIZE)):
            end = min(start + BATCH_SIZE, TOTAL_TRANSACTIONS)
            rows = [
                (
                    random.choice(account_ids),
                    random.choice(type_ids),
                    round(random.uniform(10, 10_000), 2),
                    round(random.uniform(100, 1_000_000), 2),
                    fake.sentence(nb_words=5),
                    random.choice(statuses),
                    fake.date_time_between(start_date="-180d", end_date="now"),
                    fake.date_between(start_date="-180d", end_date="today"),
                )
                for _ in range(end - start)
            ]
            cur.executemany(
                """
                INSERT INTO transactions
                  (account_id, transaction_type_id, amount, balance_after,
                   description, status, created_at, transaction_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
            conn.commit()

    print(f"  ✓ {count_rows(conn, 'transactions'):,} transactions")


# ── Step 4: schema embeddings (optional) ──────────────────────────────────────────
def seed_embeddings(conn: psycopg.Connection) -> None:
    """
    Generate and store sentence-transformer embeddings for schema_context rows
    that are still NULL. Safe to call repeatedly — skips rows that already have
    an embedding. If the library is absent, the backend generates embeddings on
    demand and caches them in Redis.
    """
    print("\n📝 Generating schema embeddings...")

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("  ⚠  sentence-transformers not available — skipping")
        print("     (embeddings are generated at runtime and cached in Redis)")
        return

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, table_name, column_name, description "
            "FROM schema_context WHERE embedding IS NULL"
        )
        rows = cur.fetchall()

    if not rows:
        print("  ✓ All schema rows already have embeddings")
        return

    print(f"  Loading model (first run downloads ~90 MB)…")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    texts = [f"{r[1]}.{r[2]}: {r[3]}" for r in rows]
    vecs  = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)

    with conn.cursor() as cur:
        for (row_id, *_), vec in zip(rows, vecs):
            cur.execute(
                "UPDATE schema_context SET embedding = %s WHERE id = %s",
                (vec.tolist(), row_id),
            )
    conn.commit()
    print(f"  ✓ {len(rows)} embeddings written")


# ── Summary ───────────────────────────────────────────────────────────────────────
def print_summary(conn: psycopg.Connection) -> None:
    print("\n─── Final Row Counts ──────────────────────────────────────")
    for table in [
        "customers", "accounts", "transactions",
        "branches", "transaction_types", "schema_context",
    ]:
        print(f"  {table:<25} {count_rows(conn, table):>10,}")
    print("──────────────────────────────────────────────────────────")


# ── Entry point ───────────────────────────────────────────────────────────────────
def main() -> None:
    print("=" * 60)
    print("EchoSQL Database Seeding")
    print("=" * 60)
    t0 = time.time()

    conn = connect()
    print("✓ Connected to PostgreSQL")

    try:
        # Always start from a clean slate (idempotent)
        truncate_seeded_tables(conn)

        # Load static reference IDs — these are never truncated
        branch_ids = fetch_ids(conn, "branches",          "branch_id")
        type_ids   = fetch_ids(conn, "transaction_types", "type_id")

        if not branch_ids:
            sys.exit(
                "✗ branches table is empty — load the schema first:\n"
                "  psql -U postgres -d echosql -f backend/database/schema.sql"
            )
        if not type_ids:
            sys.exit(
                "✗ transaction_types table is empty — load the schema first."
            )

        print(f"  ℹ  {len(branch_ids)} branches, {len(type_ids)} transaction types available")

        # Seed in FK dependency order; each function passes actual IDs down
        customer_ids = seed_customers(conn)
        account_ids  = seed_accounts(conn, customer_ids, branch_ids)
        seed_transactions(conn, account_ids, type_ids)
        seed_embeddings(conn)

        print_summary(conn)
        print(f"\n✓ Completed in {time.time() - t0:.1f}s")

    except Exception as exc:
        conn.rollback()
        print(f"\n✗ Seeding failed: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
