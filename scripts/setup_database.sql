-- ==========================================
-- Restaurant Assistant: one-time PostgreSQL setup
-- ==========================================
-- Run as the postgres superuser from PowerShell:
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -f scripts/setup_database.sql
--
-- Safe to run again: existing roles and databases are kept.
-- No password is stored here; psql asks for it with hidden input.

-- Stop at the first error instead of continuing half-configured
\set ON_ERROR_STOP on

-- Create the application login role if it does not exist yet
SELECT 'CREATE ROLE restaurant_assistant_app LOGIN'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'restaurant_assistant_app')
\gexec

-- Set (or reset) its password; psql prompts twice and sends it encrypted
\echo 'Choose a password for restaurant_assistant_app:'
\password restaurant_assistant_app

-- Create both databases owned by the app role, so it can create its own tables
SELECT 'CREATE DATABASE restaurant_assistant OWNER restaurant_assistant_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'restaurant_assistant')
\gexec

SELECT 'CREATE DATABASE restaurant_assistant_test OWNER restaurant_assistant_app'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'restaurant_assistant_test')
\gexec

-- Show the result
SELECT datname AS database, pg_get_userbyid(datdba) AS owner
FROM pg_database
WHERE datname LIKE 'restaurant_assistant%';
