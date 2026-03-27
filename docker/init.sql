-- step 1: tạo DB (không IF NOT EXISTS)
SELECT 'CREATE DATABASE dherta'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'dherta'
)\gexec

-- step 2: connect sang DB đó
\connect dherta

-- step 3: enable extension
CREATE EXTENSION IF NOT EXISTS vector;