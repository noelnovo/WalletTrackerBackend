# Approved production release — scoped operations handoff

**Current owner correction:** GitHub Actions owns workflows and APK publication;
GitLab is passive backup only. See `GITHUB-MIGRATION.md` and the new
`github-actions-vault-plan.json`. Earlier GitLab-role/publication paragraphs below
are historical receipts, not instructions to activate GitLab or request an upload
PAT. GitHub publication uses built-in job-scoped `GITHUB_TOKEN`. Current GitHub
scan/delivery readiness remains fail-closed until authorized OIDC/network cutover.

Owner authorized production promotion, reviewed `dev` to `main` merges, a signed
WalletTracker GitHub release, a fresh one-off encrypted off-cluster MariaDB
backup/restore verification, and a brief WalletTracker-only write-freeze/read-lock
window for consistency and migration. No backup schedule, Kubernetes backup Job
or backup PVC is authorized. No device connection is required for operations.

## Verified boundaries — do not repeat

The separate Malza operator supports `run-prod /absolute/root-owned/task.py`.
Default `run` stays DEV-only. Complete production records were CAS-staged unchanged,
all six delivery records match, and exact additive read grants below were verified.
Administrator-configured Android roles match the published plan; temporary recovery
access is revoked and recovery is closed. Do not self-grant privileges, repeat
staging writes, reopen recovery, or broaden application/CI identities.

Protected staging receipt on Malza (NOT backup/restore or release approval):
`/var/lib/wallettracker-production-operations/vault-stage-20261106T073611Z.json`.

## Vault production inputs — preserve all existing values

Recheck privately the already-staged complete production records from
`downops/apps/wallettracker/{runtime,rsa,signing,mobile}` to
`downops/apps/wallettracker/prod/{runtime,rsa,signing,mobile}`. If a target differs,
stop; do not overwrite or regenerate credentials or blindly stage again. Shared canonical
delivery records already match their legacy sources. Keep old records/grants.

Already-added exact new-path READ grants on these existing reader policies must
remain additive, retaining old grants until verified cutover and retirement approval:

- `wallettracker-prod-database`: canonical `prod/runtime`.
- `wallettracker-prod-identity`: canonical `prod/rsa` and `prod/signing`.
- `wallettracker-prod-pull`: canonical `delivery/harbor-pull`.
- `wallettracker-ci-prod`: canonical `delivery/{harbor-ci,github-mirror,argocd-prod}`.
- `wallettracker-repository`: canonical `delivery/gitops-read`; coordinate global
  credentials GitOps on protected main, never leave an unmanaged live patch.

Do not change JWT issuer/trust, namespaces or existing role bindings/TTLs.
Production APK signing MUST retain public certificate SHA256
`60b988457cca109d8f3a1f3ad288f95648f9938990aeedff0dfc5ed479952b61`, independently
verified from published v2.2.2. This public fingerprint is not a secret hash.
No production APK/server RSA/DB password/SSH key/robot/Argo token rotations.

## Android CI and GitHub release permissions

The exact protected-tag production signing and publication roles were configured
by the administrator from Android `delivery/production-signing-vault-plan.json`
at `e274a8a89ae332a2530a37a4347ca2cf414ae171`. Verify rather than recreate them. Use the
repaired request encoding (server helper revision3a937b2), preserve project31,
namespace downops, protected `v*` tag and900s batch restrictions. Signing identity
may read only `downops/data/apps/wallettracker/prod/mobile`; publication identity
may read only `downops/data/apps/wallettracker/delivery/github-release`.

Owner now requires all pipeline jobs, including publication, to run in GitLab;
GitHub remains the mirror and release-download host, not a workflow runner.
Keep the existing estate credential server-side; do not copy it into CI or expose
values in chat. The distinct repository-only `GITHUB_RELEASE_TOKEN` remains absent
from `downops/apps/wallettracker/delivery/github-release`. GitLab publication is
gated off with `GITHUB_RELEASE_READY=false` until it is provisioned/verified.
Real production release signing and asset upload remain gates to test; an explicit
nonpublishing protected-tag signing check cannot authorize a production release.

## Recovery and cutover sequence

Synthetic sandbox/envelope/off-cluster transport readiness is recorded in
`/var/lib/wallettracker-production-operations/readiness-20261106T092637Z/readiness-receipt.json`.
Controller test receipts `unit-{a,b,c}-receipt.json` are under
`/var/lib/wallettracker-production-operations/controller-review-20261106/`.
The real synthetic watchdog released its owned session in117.453 seconds.
These are NOT production backup/restore proof. The production adapter must be
reviewed with exact target/ownership guards; synthetic test accounts must never
be created in production. Recheck sandbox lifetime/capacity before use.

1. Establish current production health and signing/value/read-grant equality.
2. Coordinate the approved write/DDL/account-change quiescence/read-lock window.
   Financial tables are InnoDB, but account/definition tables are Aria;
   single-transaction alone is not complete checkpoint proof under changes.
3. Encrypt before persistent storage; take the fresh off-cluster snapshot including
   main/tenant data and accounts/grants. Restore-test in an isolated non-public,
   non-dev sandbox with no finance-content/secret/hash output. Record protected
   paths, timestamp, integrity/equality booleans and counts. No production data in dev.
4. Only after proof, approve the release-specific checkpoint described by
   `release-checkpoint-schema.sql` for `wallettracker-api-v2` with verified restore,
   verified write-freeze and fresh backup metadata. Old restore id1 is not new proof.
   No automatic CI or migration may create an approval.
   If writes resume after capture, the snapshot remains a recovery point, not
   automatically cutover-fresh proof. Compare complete private application,
   account/grant and definition state under final quiescence. Stop on mismatch;
   never treat counts or unchanged Alembic heads alone as data equality.
5. Parent coordinates protected-main merges/mirror equality, backend protected
   release/manual Argo sync and actual Ready/migration/data proof. Do not deploy
   a stale writer or restore an old snapshot after new writes without current-data
   transfer. Stop on any failed readiness/signature/migration/security gate.
6. Android GitLab `prod-apk` builds/signs/verifies; GitLab `publish-prod` uses its
   distinct repository-scoped credential, checks source/tag, release purpose,
   APK configuration/signature, live API-v2 and checksums, uploads verified CI
   assets to a draft, verifies digests and only then publishes to GitHub Releases.
   It remains gated off until its credential is verified. No GitHub Actions run.
   No unsigned/debug APK release; no installed-app uninstall or signer change.

Return non-secret receipts at each boundary. No old production/shared-source
deletion until every active reader is verified on canonical paths.
