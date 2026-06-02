-- migrate_to_section_level.sql
-- Migrates the chunks table from voyage-law-2 (vector(1024), paragraph-level)
-- to text-embedding-3-small (vector(1536), section-level).
--
-- Run as:
--   sudo -u postgres psql < scripts/migrate_to_section_level.sql
-- Or connect to the regulation_rag database directly:
--   psql postgresql://regulation_app:regulation_dev_password@localhost:5432/regulation_rag < scripts/migrate_to_section_level.sql

\c regulation_rag

-- Step 1: Remove all existing voyage-law-2 paragraph embeddings
TRUNCATE TABLE chunks;

-- Step 2: Change the embedding column dimension from 1024 (voyage-law-2)
--         to 1536 (text-embedding-3-small)
ALTER TABLE chunks DROP COLUMN embedding;
ALTER TABLE chunks ADD COLUMN embedding vector(1536);

-- Step 3: Verify
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_name = 'chunks' AND column_name = 'embedding';

-- Expected output:
--  column_name | data_type | udt_name
-- -------------+-----------+-----------
--  embedding   | USER-DEFINED | vector
-- The dimension is stored in the type definition — verify with:
SELECT pg_catalog.format_type(atttypid, atttypmod)
FROM pg_attribute
WHERE attrelid = 'chunks'::regclass AND attname = 'embedding';
-- Expected: vector(1536)

\echo 'Migration complete. embedding column is now vector(1536).'
\echo 'Next: set EMBEDDING_MODEL=text-embedding-3-small and CHUNK_STRATEGY=section in .env'
\echo 'Then run: python src/ingest.py --titles 7 21 42'
