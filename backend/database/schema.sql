-- EchoSQL Database Schema - Banking Domain
-- Creates 5 banking tables (200k+ rows) + embedding cache tables

-- =====================================================
-- Enable pgvector extension
-- =====================================================
CREATE EXTENSION IF NOT EXISTS vector;

-- =====================================================
-- Banking Domain Tables (Star Schema)
-- =====================================================

-- 1. Customers dimension table
CREATE TABLE IF NOT EXISTS customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(20),
    account_type VARCHAR(50) NOT NULL CHECK (account_type IN ('Savings', 'Checking', 'Premium', 'Business')),
    kyc_status VARCHAR(20) NOT NULL CHECK (kyc_status IN ('Verified', 'Pending', 'Rejected')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_customers_account_type ON customers(account_type);
CREATE INDEX idx_customers_kyc_status ON customers(kyc_status);

-- 2. Branches dimension table
CREATE TABLE IF NOT EXISTS branches (
    branch_id SERIAL PRIMARY KEY,
    branch_code VARCHAR(20) UNIQUE NOT NULL,
    location VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(50),
    country VARCHAR(100) NOT NULL,
    manager_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_branches_city ON branches(city);
CREATE INDEX idx_branches_country ON branches(country);

-- 3. Accounts table (facts)
CREATE TABLE IF NOT EXISTS accounts (
    account_id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    branch_id INTEGER NOT NULL REFERENCES branches(branch_id),
    account_number VARCHAR(30) UNIQUE NOT NULL,
    account_type VARCHAR(50) NOT NULL CHECK (account_type IN ('Savings', 'Checking', 'Premium', 'Business')),
    balance DECIMAL(15, 2) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL CHECK (status IN ('Active', 'Inactive', 'Frozen')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_accounts_customer_id ON accounts(customer_id);
CREATE INDEX idx_accounts_branch_id ON accounts(branch_id);
CREATE INDEX idx_accounts_status ON accounts(status);
CREATE INDEX idx_accounts_balance ON accounts(balance);

-- 4. Transaction types dimension
CREATE TABLE IF NOT EXISTS transaction_types (
    type_id SERIAL PRIMARY KEY,
    type_name VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255),
    category VARCHAR(50) NOT NULL CHECK (category IN ('Deposit', 'Withdrawal', 'Transfer', 'Fee', 'Interest'))
);

CREATE INDEX idx_transaction_types_category ON transaction_types(category);

-- 5. Transactions fact table
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id BIGSERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(account_id),
    transaction_type_id INTEGER NOT NULL REFERENCES transaction_types(type_id),
    amount DECIMAL(15, 2) NOT NULL,
    balance_after DECIMAL(15, 2),
    description VARCHAR(255),
    status VARCHAR(20) NOT NULL CHECK (status IN ('Completed', 'Pending', 'Failed')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    transaction_date DATE DEFAULT CURRENT_DATE
);

CREATE INDEX idx_transactions_account_id ON transactions(account_id);
CREATE INDEX idx_transactions_type_id ON transactions(transaction_type_id);
CREATE INDEX idx_transactions_created_at ON transactions(created_at);
CREATE INDEX idx_transactions_transaction_date ON transactions(transaction_date);
CREATE INDEX idx_transactions_amount ON transactions(amount);

-- =====================================================
-- Embedding Storage Tables (for Redis + pgvector fallback)
-- =====================================================

-- Query cache with embeddings
CREATE TABLE IF NOT EXISTS query_cache (
    id BIGSERIAL PRIMARY KEY,
    user_query TEXT NOT NULL,
    generated_sql TEXT NOT NULL,
    result_hash VARCHAR(64),
    embedding vector(384),
    hit_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX idx_query_cache_hash ON query_cache(result_hash);
CREATE INDEX idx_query_cache_created_at ON query_cache(created_at);
CREATE INDEX idx_query_cache_embedding ON query_cache USING hnsw (embedding vector_cosine_ops);

-- Schema context embeddings (for semantic search on table descriptions)
CREATE TABLE IF NOT EXISTS schema_context (
    id BIGSERIAL PRIMARY KEY,
    table_name VARCHAR(255) NOT NULL,
    column_name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(table_name, column_name)
);

CREATE INDEX idx_schema_context_table ON schema_context(table_name);
CREATE INDEX idx_schema_context_embedding ON schema_context USING hnsw (embedding vector_cosine_ops);

-- =====================================================
-- Initial Data: Transaction Types
-- =====================================================

INSERT INTO transaction_types (type_name, description, category) VALUES
    ('Deposit', 'Money deposited into account', 'Deposit'),
    ('Withdrawal', 'Cash withdrawal from account', 'Withdrawal'),
    ('Transfer Out', 'Money transferred to another account', 'Transfer'),
    ('Transfer In', 'Money received from another account', 'Transfer'),
    ('ATM Withdrawal', 'Cash withdrawn from ATM', 'Withdrawal'),
    ('Online Transfer', 'Transfer via online banking', 'Transfer'),
    ('Salary Deposit', 'Salary or payroll deposit', 'Deposit'),
    ('Bill Payment', 'Payment for bills', 'Withdrawal'),
    ('Interest', 'Interest credited to account', 'Interest'),
    ('Maintenance Fee', 'Monthly account maintenance fee', 'Fee'),
    ('Overdraft Fee', 'Overdraft charge', 'Fee'),
    ('ATM Fee', 'Fee for ATM usage', 'Fee'),
    ('Wire Transfer', 'Wire transfer of funds', 'Transfer'),
    ('Check Deposit', 'Check deposited into account', 'Deposit'),
    ('Refund', 'Refund to account', 'Deposit')
ON CONFLICT DO NOTHING;

-- =====================================================
-- Initial Data: Branches (Sample)
-- =====================================================

INSERT INTO branches (branch_code, location, city, state, country, manager_name) VALUES
    ('NYC001', '123 Broadway, New York', 'New York', 'NY', 'USA', 'John Smith'),
    ('NYC002', '456 Park Ave, New York', 'New York', 'NY', 'USA', 'Sarah Johnson'),
    ('LAX001', '789 Santa Monica Blvd, Los Angeles', 'Los Angeles', 'CA', 'USA', 'Michael Brown'),
    ('CHI001', '321 Michigan Ave, Chicago', 'Chicago', 'IL', 'USA', 'Emily Davis'),
    ('MIA001', '654 Biscayne Blvd, Miami', 'Miami', 'FL', 'USA', 'David Wilson'),
    ('SF001', '987 Market St, San Francisco', 'San Francisco', 'CA', 'USA', 'Jennifer Garcia'),
    ('BOS001', '111 Hanover St, Boston', 'Boston', 'MA', 'USA', 'Robert Martinez'),
    ('SEA001', '222 Pike Place, Seattle', 'Seattle', 'WA', 'USA', 'Lisa Anderson'),
    ('DEN001', '333 16th St, Denver', 'Denver', 'CO', 'USA', 'James Taylor'),
    ('AUS001', '444 Congress Ave, Austin', 'Austin', 'TX', 'USA', 'Patricia Thomas')
ON CONFLICT DO NOTHING;

-- =====================================================
-- Stored Procedures and Views
-- =====================================================

-- View: Customer Account Summary
CREATE OR REPLACE VIEW customer_account_summary AS
SELECT 
    c.customer_id,
    c.name,
    c.email,
    COUNT(a.account_id) as num_accounts,
    SUM(a.balance) as total_balance,
    AVG(a.balance) as avg_balance,
    c.created_at
FROM customers c
LEFT JOIN accounts a ON c.customer_id = a.customer_id
GROUP BY c.customer_id, c.name, c.email, c.created_at;

-- View: Transaction Summary by Type
CREATE OR REPLACE VIEW transaction_summary_by_type AS
SELECT 
    tt.type_name,
    tt.category,
    COUNT(t.transaction_id) as transaction_count,
    SUM(t.amount) as total_amount,
    AVG(t.amount) as avg_amount,
    MIN(t.created_at) as first_transaction,
    MAX(t.created_at) as last_transaction
FROM transaction_types tt
LEFT JOIN transactions t ON tt.type_id = t.transaction_type_id
GROUP BY tt.type_id, tt.type_name, tt.category;

-- View: Branch Performance
CREATE OR REPLACE VIEW branch_performance AS
SELECT 
    b.branch_id,
    b.branch_code,
    b.location,
    b.city,
    COUNT(DISTINCT a.account_id) as num_accounts,
    COUNT(DISTINCT a.customer_id) as num_customers,
    SUM(a.balance) as total_deposits,
    AVG(a.balance) as avg_account_balance
FROM branches b
LEFT JOIN accounts a ON b.branch_id = a.branch_id
GROUP BY b.branch_id, b.branch_code, b.location, b.city;

-- =====================================================
-- Schema Metadata for Schema Context Table
-- =====================================================

INSERT INTO schema_context (table_name, column_name, description) VALUES
    ('customers', 'customer_id', 'Unique identifier for customer'),
    ('customers', 'name', 'Customer full name'),
    ('customers', 'email', 'Customer email address'),
    ('customers', 'phone', 'Customer phone number'),
    ('customers', 'account_type', 'Type of account: Savings, Checking, Premium, Business'),
    ('customers', 'kyc_status', 'KYC verification status: Verified, Pending, Rejected'),
    
    ('accounts', 'account_id', 'Unique identifier for account'),
    ('accounts', 'customer_id', 'References customers table'),
    ('accounts', 'branch_id', 'References branches table'),
    ('accounts', 'account_number', 'Unique account number'),
    ('accounts', 'account_type', 'Type of account: Savings, Checking, Premium, Business'),
    ('accounts', 'balance', 'Current account balance'),
    ('accounts', 'status', 'Account status: Active, Inactive, Frozen'),
    
    ('transactions', 'transaction_id', 'Unique transaction identifier'),
    ('transactions', 'account_id', 'References accounts table'),
    ('transactions', 'transaction_type_id', 'References transaction_types table'),
    ('transactions', 'amount', 'Transaction amount in dollars'),
    ('transactions', 'balance_after', 'Account balance after transaction'),
    ('transactions', 'description', 'Transaction description'),
    ('transactions', 'status', 'Transaction status: Completed, Pending, Failed'),
    ('transactions', 'created_at', 'When transaction occurred'),
    ('transactions', 'transaction_date', 'Date of transaction'),
    
    ('branches', 'branch_id', 'Unique branch identifier'),
    ('branches', 'branch_code', 'Branch code'),
    ('branches', 'location', 'Branch full location address'),
    ('branches', 'city', 'Branch city'),
    ('branches', 'state', 'Branch state'),
    ('branches', 'country', 'Branch country'),
    ('branches', 'manager_name', 'Branch manager name'),
    
    ('transaction_types', 'type_id', 'Unique transaction type identifier'),
    ('transaction_types', 'type_name', 'Name of transaction type'),
    ('transaction_types', 'description', 'Description of transaction type'),
    ('transaction_types', 'category', 'Category: Deposit, Withdrawal, Transfer, Fee, Interest')
ON CONFLICT (table_name, column_name) DO NOTHING;

-- =====================================================
-- Verify Extension and Tables
-- =====================================================

-- Check pgvector
SELECT * FROM pg_extension WHERE extname='vector';

-- Count tables created
SELECT COUNT(*) as tables_created FROM information_schema.tables 
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';

-- List all tables
\dt
