# Database Setup Guide

Complete instructions for setting up the EchoSQL database schema and seeding it with 200k+ rows of realistic banking data.

## Architecture

**Database**: PostgreSQL 15 with pgvector extension
**Schema**: Star schema with 5 banking tables + 2 embedding cache tables
**Total Rows**: 200,000+ (100k customers + 50k accounts + 200k transactions)
**Embedding Storage**: pgvector + Redis caching

---

## Step 1: Create Database

### Create PostgreSQL Database

```bash
# Connect to PostgreSQL as superuser
psql -U postgres

# Create database
postgres=# CREATE DATABASE echosql;
postgres=# \c echosql

# Verify connection
echosql=# SELECT 1;
```

### Alternative: Command Line

```bash
# Create database directly
createdb -U postgres echosql

# Connect to database
psql -U postgres -d echosql
```

---

## Step 2: Load Schema

### Option A: Using SQL File (Recommended)

```bash
# Load entire schema at once
psql -U postgres -d echosql -f backend/database/schema.sql

# Or from within psql:
# echosql=# \i backend/database/schema.sql
```

### Option B: Manual Verification

```bash
# Verify pgvector extension
echosql=# SELECT * FROM pg_extension WHERE extname='vector';

# List created tables
echosql=# \dt

# Expected tables:
# - customers
# - accounts
# - branches
# - transactions
# - transaction_types
# - query_cache
# - schema_context
```

### Verify Schema Creation

```bash
# Check table counts
echosql=# SELECT COUNT(*) as tables_created FROM information_schema.tables 
         WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
# Should return: 7

# Check pgvector is active
echosql=# SELECT * FROM pg_extension WHERE extname='vector';
# Should show vector extension

# Check schema metadata
echosql=# SELECT COUNT(*) FROM schema_context;
# Should show 33 schema entries (table + column descriptions)
```

---

## Step 3: Seed Database

### Before Seeding: Install Dependencies

```bash
cd backend

# Create virtual environment (if not already done)
python -m venv venv
venv\Scripts\activate

# Upgrade pip
pip install --upgrade pip

# Install requirements (including Faker and psycopg)
pip install -r requirements.txt
# This takes 3-5 minutes

# Verify installations
python -c "import faker; import psycopg; print('✓ Ready to seed')"
```

### Create .env File

```bash
# Copy environment template
cp .env.example .env

# Edit .env (optional - defaults work for local development)
# Defaults assume:
# - PostgreSQL on localhost:5432
# - Username: postgres
# - Password: password
# - Database: echosql
```

### Run Seeding Script

```bash
# From backend directory with venv activated
python database/seed_data.py

# This will:
# 1. Generate 100,000 customers
# 2. Generate 50,000 accounts
# 3. Generate 200,000 transactions
# 4. Generate embeddings for schema context
# 5. Display progress bars and statistics
# 
# Expected runtime: 5-15 minutes (depending on machine)
```

### Monitor Progress

The seeding script shows progress with:
- Batch completion progress bars
- Row counts for each table
- Embedding generation status
- Final verification summary

Example output:
```
📝 Seeding 100,000 customers...
100%|████████████| 10/10 [00:45<00:00,  4.50s/batch]
✓ Inserted 100,000 customers

📝 Seeding 50,000 accounts...
100%|████████████| 5/5 [00:22<00:00,  4.40s/batch]
✓ Inserted 50,000 accounts

📝 Seeding 200,000 transactions...
100%|████████████| 20/20 [01:30<00:00,  4.50s/batch]
✓ Inserted 200,000 transactions

✓ Data Verification:
  customers......................  100,000 rows
  accounts........................   50,000 rows
  transactions....................  200,000 rows
  transaction_types...............       15 rows
  branches.........................       10 rows
  schema_context...................       33 rows
  query_cache......................        0 rows
```

---

## Step 4: Verify Data

### Check Table Sizes

```bash
echosql=# SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    (SELECT COUNT(*) FROM (SELECT 1 FROM information_schema.tables) t) as row_count
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Sample Queries to Test

```bash
# Test 1: Customer count
echosql=# SELECT COUNT(*) FROM customers;
# Expected: ~100,000

# Test 2: Account balances
echosql=# SELECT SUM(balance) as total_balance, AVG(balance) as avg_balance FROM accounts;
# Expected: ~$2.5 billion total, ~$50,000 avg

# Test 3: Transaction volume
echosql=# SELECT COUNT(*) FROM transactions WHERE created_at > CURRENT_DATE - INTERVAL '30 days';
# Expected: varies, but should have recent transactions

# Test 4: Join query (2 tables)
echosql=# SELECT 
    c.name, 
    COUNT(a.account_id) as num_accounts,
    SUM(a.balance) as total_balance
FROM customers c
LEFT JOIN accounts a ON c.customer_id = a.customer_id
GROUP BY c.customer_id, c.name
ORDER BY total_balance DESC
LIMIT 10;

# Test 5: Join query (3 tables)
echosql=# SELECT 
    c.name,
    COUNT(DISTINCT t.transaction_id) as num_transactions,
    SUM(t.amount) as total_transactions,
    AVG(t.amount) as avg_transaction
FROM customers c
JOIN accounts a ON c.customer_id = a.customer_id
JOIN transactions t ON a.account_id = t.account_id
GROUP BY c.customer_id, c.name
ORDER BY total_transactions DESC
LIMIT 10;
```

---

## Step 5: Test with Views

The schema includes 3 pre-built views for common queries:

### Customer Account Summary View

```bash
echosql=# SELECT * FROM customer_account_summary 
         WHERE total_balance > 500000 
         ORDER BY total_balance DESC
         LIMIT 10;

# Shows:
# - Customer name, email
# - Number of accounts
# - Total and average balance
# - Account creation date
```

### Transaction Summary by Type

```bash
echosql=# SELECT * FROM transaction_summary_by_type 
         WHERE category = 'Withdrawal'
         ORDER BY transaction_count DESC;

# Shows:
# - Transaction type and category
# - Count and total amount
# - First and last transaction dates
```

### Branch Performance View

```bash
echosql=# SELECT * FROM branch_performance 
         ORDER BY num_accounts DESC 
         LIMIT 5;

# Shows:
# - Branch info (code, location, city)
# - Number of customers and accounts
# - Total deposits
```

---

## Troubleshooting

### "Database already exists"

```bash
# Drop existing database and recreate
psql -U postgres -c "DROP DATABASE IF EXISTS echosql;"
psql -U postgres -c "CREATE DATABASE echosql;"
psql -U postgres -d echosql -f backend/database/schema.sql
```

### "pgvector extension not found"

```bash
# pgvector may not be installed
# See REDIS_SETUP.md for pgvector installation instructions
# Or skip pgvector and use just Redis caching:
psql -U postgres -d echosql -c "CREATE EXTENSION vector;" # Will fail gracefully if not installed
```

### Seeding Script Fails: "Connection refused"

```bash
# Verify PostgreSQL is running
psql -U postgres -c "SELECT 1;"

# Check connection settings in .env
cat .env | grep DATABASE_URL

# Default should be: postgresql://postgres:password@localhost:5432/echosql
```

### Seeding Takes Too Long

The seeding process involves:
- Generating 350,000 rows of fake data
- Computing 768-dimensional embeddings for 33 schema items
- Batch inserting with integrity checks

**Expected times:**
- First run (includes embedding model download): 10-20 minutes
- Subsequent runs (model cached): 5-10 minutes

To speed up:
- Reduce `TOTAL_CUSTOMERS`, `TOTAL_ACCOUNTS`, `TOTAL_TRANSACTIONS` in `seed_data.py`
- Increase `BATCH_SIZE` if machine has plenty of RAM
- Disable embedding generation (comment out in `main()`)

### Memory Issues During Seeding

```bash
# If you run out of memory:
# 1. Reduce batch size
# 2. Run on machine with more RAM
# 3. Reduce total row counts

# Edit seed_data.py:
# BATCH_SIZE = 5000  # Reduce from 10000
# TOTAL_CUSTOMERS = 50_000  # Reduce from 100_000
```

### "Embedding model download failed"

The first time you seed, it downloads `all-MiniLM-L6-v2` (80MB):

```bash
# If download fails:
# 1. Check internet connection
# 2. Manually download:
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# 3. Retry seeding
python database/seed_data.py
```

---

## Database Statistics

After successful seeding:

| Metric | Value |
|--------|-------|
| Total Customers | 100,000 |
| Total Accounts | 50,000 |
| Total Transactions | 200,000+ |
| Total Tables | 7 |
| Total Indexes | 20+ |
| Database Size | ~1-2 GB |
| Average Query Time | 50-500 ms |

---

## Maintenance

### Backup Database

```bash
# Full backup
pg_dump -U postgres echosql > echosql_backup.sql

# Restore from backup
psql -U postgres -d echosql < echosql_backup.sql
```

### Check Index Health

```bash
echosql=# SELECT schemaname, tablename, indexname, idx_scan 
         FROM pg_stat_user_indexes 
         WHERE schemaname = 'public'
         ORDER BY idx_scan DESC;
```

### Analyze Query Performance

```bash
echosql=# EXPLAIN ANALYZE 
SELECT c.name, COUNT(*) as transaction_count 
FROM customers c
JOIN accounts a ON c.customer_id = a.customer_id
JOIN transactions t ON a.account_id = t.account_id
GROUP BY c.customer_id, c.name
LIMIT 10;
```

### Vacuum and Analyze (Maintenance)

```bash
# Clean up dead tuples and analyze query planner stats
echosql=# VACUUM ANALYZE;
```

---

## Next Steps

1. ✓ Database created and schema loaded
2. ✓ 200k+ rows seeded with realistic data
3. ✓ Embeddings generated for schema context
4. **Next**: Set up FastAPI backend to use this database
5. **Then**: Connect Next.js frontend to API

See `QUICKSTART.md` for running the full application.
