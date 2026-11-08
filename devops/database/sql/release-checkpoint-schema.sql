-- MANUAL OPERATOR STEP ONLY. This creates no approval and takes no backup.
-- Populate a release row only after the approved encrypted off-cluster snapshot,
-- isolated restore verification, and confirmed WalletTracker write-freeze.
-- Never call this file or create approval rows from automatic CI/migrations.
CREATE DATABASE IF NOT EXISTS wallettracker_migration_metadata;
CREATE TABLE IF NOT EXISTS wallettracker_migration_metadata.release_checkpoint (
    name VARCHAR(64) PRIMARY KEY,
    backup_identifier VARCHAR(512) NOT NULL,
    backup_created_at TIMESTAMP NOT NULL,
    approved_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    restore_verified BOOLEAN NOT NULL DEFAULT FALSE,
    write_freeze_verified BOOLEAN NOT NULL DEFAULT FALSE
);
