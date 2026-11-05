# WalletTracker Vault layout

**Current follow-up:** the operations MCP verified unchanged-value staging of
all nine backend/delivery records and canonical reads by dev database, identity
and pull identities. Dev consumer definitions now use the canonical sources;
rollout verification is pending. Old sources/grants and production/global
readers remain untouched. Android key staging is valid, but its CI JWT role
creation is still blocked by HTTP403; CI signing stays disabled.
Non-secret proof: [vault-dev-staging-receipt.json](vault-dev-staging-receipt.json).
The handoff is [DOWNOPS-VAULT-HANDOFF.md](DOWNOPS-VAULT-HANDOFF.md).

The canonical app namespace is **KV-v2 mount `downops`, prefix
`apps/wallettracker`**. Do not introduce another top-level engine for new
WalletTracker secrets. Logical paths below omit Vault's API-only `/data/` segment.

## Existing records have different purposes

| Record | Purpose |
| --- | --- |
| `downops/apps/wallettracker/prod/mobile` | Owner-specified **production** Android keystore and build configuration |
| `downops/apps/wallettracker/prod/signing` | Legacy backend API-v1 `SIGN_SECRET_WORD`; **not** an APK signing key |
| `downops/apps/wallettracker/prod/rsa` | Production server identity/JWT RSA key pair |
| `downops/apps/wallettracker/prod/runtime` | Production database/runtime credential |
| `downops/apps/wallettracker/dev/{runtime,rsa,signing}` | Verified unchanged-value dev records; old `wallettracker/dev/*` sources retained until rollout/cleanup proof |
| `downops/apps/wallettracker/delivery/*` | Verified canonical shared delivery records; dev readers switch now, production/global readers retain their old sources until approved cutover |

Similar names across dev/prod do not establish equal secret values. Phase1
privately verified equality of all nine migrated backend/delivery records; no
secret values or hashes are exported. These are temporary migration copies,
not an excuse to reuse production credentials in development or delete sources
before their readers are migrated.

## Corrected Android development record

Use **`downops/apps/wallettracker/dev/mobile`**, containing a separate dev
keystore. Required keys are `KEYSTORE_BASE64`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`.
`KEY_PASSWORD` is optional only when different from the store password. Dev CI
must have read access to that exact record, never the production `mobile` record.

The proposed `wallettracker/dev/android-signing` record was not created by this
task. Do not provision it or duplicate existing production keystore values there.
The Android repository contains the corrected exact-path OIDC policy/role plan.

## Existing top-level mount: coordinated consolidation, not blind deletion

Target layout for a subsequent owner-managed, unchanged-value migration:

| Current path | Canonical destination |
| --- | --- |
| `wallettracker/dev/database` | `downops/apps/wallettracker/dev/runtime` |
| `wallettracker/dev/rsa` | `downops/apps/wallettracker/dev/rsa` |
| `wallettracker/dev/signing` | `downops/apps/wallettracker/dev/signing`, only while its legacy reader is retained |
| `wallettracker/delivery/<name>` | `downops/apps/wallettracker/delivery/<name>` |
| `downops/apps/wallettracker/{runtime,rsa,signing,mobile}` | `downops/apps/wallettracker/prod/{runtime,rsa,signing,mobile}`; production plan only |

Shared delivery record names are `harbor-ci`, `harbor-pull`, `gitops-read`,
`github-mirror`, `argocd-dev`, and `argocd-prod`. Keep a single canonical copy per
credential, not duplicate delivery folders under each environment. Do not create
the superseded proposed path `dev/delivery/argocd`.

Do not regenerate passwords/keys during a path move. Stage each destination with
CAS, abort if an existing destination differs, update exact reader policies and
VSO/CI references, then verify every reader before retiring the old record and
its old ACL. A temporary verified migration copy is not a permanent duplicate
source of truth. Never remove the old engine while any reader still uses it.

Production/shared consolidation is **not applied** by the present dev-only change: delivery
records are also referenced by production pull secrets and Argo repository
credentials, whose manifests track protected `main`. Removing or moving those
records now would break production and conflict with the owner's dev-only scope.
The owner authorized DownOps dev staging, which is now verified by the protected
receipt. The Android record/read-only policy exists; its JWT-role blocker is
separate. A production-reader cutover needs its
own approved release, rather than a live patch that GitOps would undo.
