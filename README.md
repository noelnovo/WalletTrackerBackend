# WalletTracker Backend

Flask API for personal finances, consumed by the WalletTracker Android app.
Production remains at **https://api.downops.win** using API v1.

## Delivery and environments

GitLab (`downops/wallet-tracker-backend`) is authoritative; GitHub
(`noelnovo/WalletTrackerBackend`) is the mirror. Both `dev` and `main` are retained.

```text
GitLab CI -> tests / real MariaDB migrations / DT + SonarQube
          -> immutable HTTPS Harbor image
          -> environment-scoped GitOps commit + immediate ArgoCD refresh
          -> ArgoCD -> Kubernetes
Vault -> exact scoped VSO identities -> application / pull / repository secrets
```

- `dev`: automatic delivery to `wallettracker-dev`, internal-only API at
  `https://wallettracker-dev.int.downops.win`.
- `main`: approved release merge and protected `vX.Y.Z` tag, manual production
  publish and Argo sync to `wallettracker-prod`.
- CI verifies the actual Ready Deployment image and generation through ArgoCD,
  exact GitOps revision, and HTTPS API/database readiness on the build revision.
- GitHub production mirroring uses the approved operator path under existing
  protection; the CI deploy key does not gain a protection bypass.
- Kubernetes uses MariaDB **11.4.12**, preserving the main database and tenant
  schemas/accounts. The API is non-root with read-only code/root filesystem.
- Production global RSA/signing/database passwords are unchanged, read from
  canonical Vault records. No credential values belong in this repository.

Jenkins, Terraform/native WalletTracker deployment, and LXCs100/101/102 are
retired. Their old deployment files are removed, not an alternative delivery path.
Protected recovery archives remain outside Git. See
`delivery/deployment-receipt.json` for the verified cutover and retention record.

## Android

Source is maintained on GitLab `downops/wallet-tracker-android` and mirrored to
GitHub `noelnovo/WalletTracker`. It keeps the public API hostname and existing
signing/account crypto. Its readiness request checks the database, normalizes
URL slashes, and closes the HTTP response. Source updates do not publish an APK;
APK publication requires explicit manual release approval.

## Development and testing

Use Python3.12+, `uv`, and native MariaDB development libraries for mysqlclient.
Keep environments inside the repository. Never copy production data into dev.

```sh
cd app
uv sync --frozen
cd ..
ENABLE_REGISTER=true WALLET_TRACKER_STDOUT_LOG=true PYTHONPATH=app app/.venv/bin/pytest tests -q
python3 -m unittest discover -s delivery -p 'test_*.py'
python3 delivery/render_manifests.py --check
```

GitLab CI additionally tests real MariaDB main/tenant migrations, actual new
tenant registration followed by repeated migration, and managed-key startup
with synthetic read-only keys. Missing managed production identity fails closed.

## Schema and recovery safeguards

`app/migrations_main` owns User/RefreshToken; `app/migrations_tenant` owns each
tenant's finance tables. New tenant registration applies the real versioned
migration tree; request-time engine initialization must not run `create_all`.
`app/migrate_all.py` refuses unversioned existing databases rather than silently
stamping an assumed baseline. Review and test schema changes before a release.

Argo's migration hook waits for authenticated SQL and requires the manually
approved production restore checkpoint. CI never creates that checkpoint.
Changes to `delivery/environment-state.json` require review; production sync
stays manual. Production backups run daily in-cluster; off-host recovery export
is verified separately and must not be confused with automatic off-host rotation.
Database and backup PVs use Retain.

Before new-primary writes, rollback requires verified database equality. After
new writes, freeze and transfer the **current** database before restoring a prior
writer. Never restart a stale native database/API or replay retired Terraform.

## API

`/api/v1/health` is liveness; `/api/v1/ready` verifies the database.
Production registration is disabled. Authentication, expense/category, season
and income requests remain compatible with the Android client. The `bruno/`
collection contains development API requests.
