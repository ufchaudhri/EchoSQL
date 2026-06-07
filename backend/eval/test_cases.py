"""
Curated eval test cases for the EchoSQL text-to-SQL pipeline.

Each case records:
  id              — short identifier used in reports
  nl              — natural-language question sent to the LLM
  expected_tables — table/view names that MUST appear in the generated SQL
  must_have       — SQL keywords/fragments that should be present (case-insensitive)
  must_not_have   — SQL fragments that should NOT appear (safety / correctness)
  category        — query type for grouping in the report
  notes           — what to look for when reviewing results
"""

TEST_CASES = [

    # ── Simple lookups ────────────────────────────────────────────────────────
    {
        "id":              "simple_01",
        "nl":              "Show all customers",
        "expected_tables": ["customers"],
        "must_have":       ["SELECT"],
        "must_not_have":   [],
        "category":        "simple",
        "notes":           "Baseline — should return up to LIMIT 100 rows",
    },
    {
        "id":              "simple_02",
        "nl":              "List all active accounts",
        "expected_tables": ["accounts"],
        "must_have":       ["Active"],
        "must_not_have":   [],
        "category":        "simple",
        "notes":           "Must filter status = 'Active'",
    },
    {
        "id":              "simple_03",
        "nl":              "Show all branches in New York",
        "expected_tables": ["branches"],
        "must_have":       ["New York"],
        "must_not_have":   [],
        "category":        "simple",
        "notes":           "Must filter city = 'New York'",
    },
    {
        "id":              "simple_04",
        "nl":              "Find customers whose KYC status is pending",
        "expected_tables": ["customers"],
        "must_have":       ["Pending"],
        "must_not_have":   [],
        "category":        "simple",
        "notes":           "Must filter kyc_status = 'Pending'",
    },

    # ── Aggregations ──────────────────────────────────────────────────────────
    {
        "id":              "agg_01",
        "nl":              "What is the total balance across all accounts?",
        "expected_tables": ["accounts"],
        "must_have":       ["SUM", "balance"],
        "must_not_have":   ["LIMIT"],
        "category":        "aggregate",
        "notes":           "Single-row result; LIMIT should NOT be present",
    },
    {
        "id":              "agg_02",
        "nl":              "How many customers are there?",
        "expected_tables": ["customers"],
        "must_have":       ["COUNT"],
        "must_not_have":   ["LIMIT"],
        "category":        "aggregate",
        "notes":           "COUNT(*) expected",
    },
    {
        "id":              "agg_03",
        "nl":              "What is the average account balance?",
        "expected_tables": ["accounts"],
        "must_have":       ["AVG", "balance"],
        "must_not_have":   [],
        "category":        "aggregate",
        "notes":           "AVG(balance) expected",
    },
    {
        "id":              "agg_04",
        "nl":              "How many transactions were completed last month?",
        "expected_tables": ["transactions"],
        "must_have":       ["COUNT", "Completed"],
        "must_not_have":   [],
        "category":        "aggregate",
        "notes":           "Date filter + status filter",
    },
    {
        "id":              "agg_05",
        "nl":              "Total deposit amount by branch",
        "expected_tables": ["transactions", "accounts", "branches"],
        "must_have":       ["SUM", "GROUP BY"],
        "must_not_have":   [],
        "category":        "aggregate",
        "notes":           "Multi-table join with GROUP BY branch",
    },

    # ── Joins ─────────────────────────────────────────────────────────────────
    {
        "id":              "join_01",
        "nl":              "Show customer names with their account balances",
        "expected_tables": ["customers", "accounts"],
        "must_have":       ["JOIN", "balance", "name"],
        "must_not_have":   [],
        "category":        "join",
        "notes":           "Basic customers ↔ accounts join",
    },
    {
        "id":              "join_02",
        "nl":              "List transactions with the customer name and transaction type",
        "expected_tables": ["transactions", "customers", "transaction_types"],
        "must_have":       ["JOIN"],
        "must_not_have":   [],
        "category":        "join",
        "notes":           "Three-table join",
    },
    {
        "id":              "join_03",
        "nl":              "Which branch has the most accounts?",
        "expected_tables": ["accounts", "branches"],
        "must_have":       ["JOIN", "COUNT", "GROUP BY"],
        "must_not_have":   [],
        "category":        "join",
        "notes":           "Aggregation with join; ORDER BY + LIMIT 1 expected",
    },
    {
        "id":              "join_04",
        "nl":              "Show customers with frozen accounts",
        "expected_tables": ["customers", "accounts"],
        "must_have":       ["JOIN", "Frozen"],
        "must_not_have":   [],
        "category":        "join",
        "notes":           "Join + filter on account status",
    },

    # ── Filtering & ordering ──────────────────────────────────────────────────
    {
        "id":              "filter_01",
        "nl":              "Find accounts with a balance over 50000",
        "expected_tables": ["accounts"],
        "must_have":       ["balance", "50000"],
        "must_not_have":   [],
        "category":        "filter",
        "notes":           "Numeric comparison",
    },
    {
        "id":              "filter_02",
        "nl":              "Show failed transactions",
        "expected_tables": ["transactions"],
        "must_have":       ["Failed"],
        "must_not_have":   [],
        "category":        "filter",
        "notes":           "Status enum filter",
    },
    {
        "id":              "filter_03",
        "nl":              "List Business account customers",
        "expected_tables": ["customers"],
        "must_have":       ["Business"],
        "must_not_have":   [],
        "category":        "filter",
        "notes":           "account_type filter on customers table",
    },

    # ── Top-N ─────────────────────────────────────────────────────────────────
    {
        "id":              "topn_01",
        "nl":              "Top 5 customers by total account balance",
        "expected_tables": ["customers", "accounts"],
        "must_have":       ["JOIN", "ORDER BY", "LIMIT"],
        "must_not_have":   [],
        "category":        "top-n",
        "notes":           "ORDER BY DESC + LIMIT 5",
    },
    {
        "id":              "topn_02",
        "nl":              "Top 10 largest transactions",
        "expected_tables": ["transactions"],
        "must_have":       ["ORDER BY", "LIMIT"],
        "must_not_have":   [],
        "category":        "top-n",
        "notes":           "ORDER BY amount DESC LIMIT 10",
    },

    # ── Date-based ────────────────────────────────────────────────────────────
    {
        "id":              "date_01",
        "nl":              "Show transactions from the last 7 days",
        "expected_tables": ["transactions"],
        "must_have":       ["transaction_date", "INTERVAL"],
        "must_not_have":   [],
        "category":        "date",
        "notes":           "Date arithmetic: transaction_date >= NOW() - INTERVAL",
    },
    {
        "id":              "date_02",
        "nl":              "How many new customers signed up this year?",
        "expected_tables": ["customers"],
        "must_have":       ["COUNT", "created_at"],
        "must_not_have":   [],
        "category":        "date",
        "notes":           "EXTRACT(YEAR ...) or DATE_TRUNC or created_at >= '2026-01-01'",
    },
]
