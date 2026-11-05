# DownOps handoff: dev-only Vault consolidation

Owner approved **dev only + production plan**. The operations MCP attempt was
blocked by `Insufficient Balance`; no staging receipt was returned. Repository
runtime readers deliberately remain on their existing paths until staging is
verified. Use `git show dev:<path>` when a clone's working tree is on `main`.

## Phase 1 — authorized staging only

Use existing authorized Vault access; no root recovery, auth bypass, password/key
rotation, database changes, app releases, production/shared-reader changes, or
`main` edits. Never print/export secret values or hashes. Preserve rollback and
version history outside Git.

Stage identical existing values with CAS-create; if a destination exists, compare
privately and abort on a difference. Keep source records and old grants for now.

| Source | Destination | Keys |
| --- | --- | --- |
| `wallettracker/dev/database` | `downops/apps/wallettracker/dev/runtime` | `DATABASE_ROOT_PASSWORD` |
| `wallettracker/dev/rsa` | `downops/apps/wallettracker/dev/rsa` | `PRIVATE_KEY_BASE64`, `PUBLIC_KEY_BASE64` |
| `wallettracker/dev/signing` | `downops/apps/wallettracker/dev/signing` | `SIGN_SECRET_WORD` |
| `wallettracker/delivery/argocd-dev` | `downops/apps/wallettracker/dev/delivery/argocd` | `TOKEN`; first prove exclusively dev-owned |

Add exact canonical reads only to `wallettracker-dev-database`,
`wallettracker-dev-identity`, and (for the exclusive Argo token) `wallettracker-ci-dev`.
Retain existing dev grants temporarily. Preserve JWT bindings, auth configuration,
TTL and all production/shared permissions. Shared Harbor/mirror reads stay as-is.

For Android, the intended path is `downops/apps/wallettracker/dev/mobile`.
Do not copy the production APK key or generate/rotate the installed dev signer.
If no genuine dev key exists, return missing-field names for the owner:
`KEYSTORE_BASE64`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`; `KEY_PASSWORD` only if distinct.
Exact optional OIDC role/policy: Android repo `delivery/dev-signing-vault-plan.json`
on `dev`. Do not enable `DEV_SIGNING_READY` until real values are validated.

Return a non-secret receipt: paths, key names, equality booleans, dev policies
changed, Argo-token exclusivity, current dev health, Android role status and
missing-field names. No values or hashes.

## Wait for repository rollout

Return the Phase 1 receipt to the coding agent. It will switch dev VSO sources,
the dev CI Argo-token read, and the active contract through the `dev` branch and
normal GitLab/Argo delivery, then provide successful pipeline/readiness/VSO proof.
`bootstrap_vault.py` is now plan-only; `--apply` cannot create another root engine
or credentials. `contract(canonical_dev=True)` renders the desired policy plan;
the default contract describes the still-active readers.

## Phase 2 — not authorized until rollout verification

Only after explicit confirmation and auditing all active readers: soft-delete
unused **old dev** records and remove their old **dev-only** grants. Retain secret
history. Do not remove the `wallettracker` engine or shared records.

## Production/shared — plan only

Do not modify `downops/apps/wallettracker/{mobile,runtime,rsa,signing}` or existing
`wallettracker/delivery/{harbor-ci,harbor-pull,gitops-read,github-mirror,argocd-prod}`.
Inventory their readers and plan one unchanged-value move per shared record to
`downops/apps/wallettracker/delivery/<name>`. Production pull/repository/CI readers
and protected-main GitOps need a separately approved coordinated cutover; never
leave a live patch that Argo will revert. Do not duplicate shared values per env.
