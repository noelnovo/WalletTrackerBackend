-- MANUAL OPERATOR STEP ONLY, after protected source/target row, grant/account,
-- main/tenant Alembic revision, RSA and signing-value equality checks succeed.
-- Never call this from an initContainer, image build or automatic CI pipeline.
CREATE DATABASE IF NOT EXISTS wallettracker_migration_metadata;
CREATE TABLE IF NOT EXISTS wallettracker_migration_metadata.restore_checkpoint
  (id TINYINT PRIMARY KEY, approved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT INTO wallettracker_migration_metadata.restore_checkpoint (id) VALUES (1);
