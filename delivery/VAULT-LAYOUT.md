# WalletTracker Vault layout

**Current follow-up:** owner specified `dev/`, `prod/`, and shared `delivery/`
under this app prefix and approved dev-only consolidation plus a production
plan. The operations MCP is blocked by `Insufficient Balance`; values, policies
and cutover have not been independently verified. Active runtime readers are unchanged. The executable
handoff is [DOWNOPS-VAULT-HANDOFF.md](DOWNOPS-VAULT-HANDOFF.md).

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
| `wallettracker/dev/database`, `wallettracker/dev/rsa`, `wallettracker/dev/signing` | Existing isolated dev identities introduced during the earlier Kubernetes cutover |
| `downops/apps/wallettracker/delivery/*` | Canonical shared Harbor, repository/mirror and Argo delivery records; existing readers still use `wallettracker/delivery/*` pending cutover |

Similar names across dev/prod do not establish equal secret values. The previous
cutover generated independent dev identities; this task has not read/exported
all current values to claim a fresh equality audit. The split between mounts is
an inherited layout inconsistency, not a reason to reuse production credentials
in development or delete live records.

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
The owner authorized DownOps to handle dev staging, but its failed attempt
returned no verified Vault changes. The Android path correction itself does not
write Vault values, policies or roles. A production-reader cutover needs its
own approved release, rather than a live patch that GitOps would undo.
