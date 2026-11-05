# DownOps handoff: dev-only Vault consolidation

Owner approved **dev only + production plan**. Phase1 backend/delivery staging
and dev read grants are now verified; see `vault-dev-staging-receipt.json`.
Dev source references are being rolled out through GitLab/Argo. Old sources and
grants remain until rollout verification; Android JWT-role creation has a
separate HTTP403 blocker. Use `git show dev:<path>` when a clone is on `main`.
Owner subsequently specified the canonical layout as
`downops/apps/wallettracker/{dev,prod}/...` plus shared `delivery/...`.

## Phase 1 — authorized staging only

Use existing authorized Vault access; no root recovery, auth bypass, existing password/key
rotation, database changes, app releases, production/shared-reader changes, or
`main` edits. Never print/export secret values or hashes. Preserve rollback and
version history outside Git.

Stage identical existing values with CAS-create; if a destination exists, compare
privately and abort on a difference. Keep source records and old grants for now.
Preserve complete existing records, including additional keys not listed below.

| Source | Destination | Keys |
| --- | --- | --- |
| `wallettracker/dev/database` | `downops/apps/wallettracker/dev/runtime` | `DATABASE_ROOT_PASSWORD` |
| `wallettracker/dev/rsa` | `downops/apps/wallettracker/dev/rsa` | `PRIVATE_KEY_BASE64`, `PUBLIC_KEY_BASE64` |
| `wallettracker/dev/signing` | `downops/apps/wallettracker/dev/signing` | `SIGN_SECRET_WORD` |
| `wallettracker/delivery/harbor-ci` | `downops/apps/wallettracker/delivery/harbor-ci` | `HARBOR_ROBOT_NAME`, `HARBOR_ROBOT_SECRET` |
| `wallettracker/delivery/harbor-pull` | `downops/apps/wallettracker/delivery/harbor-pull` | `HARBOR_ROBOT_NAME`, `HARBOR_ROBOT_SECRET` |
| `wallettracker/delivery/github-mirror` | `downops/apps/wallettracker/delivery/github-mirror` | `SSH_PRIVATE_KEY`, `KNOWN_HOSTS` |
| `wallettracker/delivery/argocd-dev` | `downops/apps/wallettracker/delivery/argocd-dev` | `TOKEN`; verify reader ownership before eventual source retirement |

Add exact canonical reads only to `wallettracker-dev-database`,
`wallettracker-dev-identity`, `wallettracker-dev-pull`, and `wallettracker-ci-dev`.
Retain existing dev grants temporarily. Preserve JWT bindings, auth configuration,
TTL and all production/shared permissions. Only dev readers switch to canonical
shared Harbor/mirror records; production readers and old shared records stay as-is.

For Android, the intended path is `downops/apps/wallettracker/dev/mobile`.
Do not copy the production APK key or rotate the installed dev signer. Reuse an
existing genuine dedicated dev keystore. If none exists, the owner's request to
create missing signing material allows staging a new dedicated JKS RSA3072 dev
key with a strong random store/key password, without installing it or changing
the current signer. Do not overwrite any existing dev key. Required fields:
`KEYSTORE_BASE64`, `KEYSTORE_PASSWORD`, `KEY_ALIAS`; `KEY_PASSWORD` only if distinct.
Exact optional OIDC role/policy: Android repo `delivery/dev-signing-vault-plan.json`
on `dev`. Do not enable `DEV_SIGNING_READY` until real values are validated.
If the staged key differs from the installed debug signer, a separate data-safe
signer-transition plan is required; never uninstall the app to bypass a mismatch.
Do not create `dev/delivery/argocd`; the Argo token belongs in shared
`delivery/argocd-dev` under the canonical app prefix.

Return a non-secret receipt: paths, key names, equality booleans, dev policies
changed, Argo-token exclusivity, current dev health, Android role status and
missing-field names. No values or hashes.

## Wait for repository rollout

Return the Phase 1 receipt to the coding agent. It will switch dev VSO sources,
the dev CI Argo-token read, and the active contract through the `dev` branch and
normal GitLab/Argo delivery, then provide successful pipeline/readiness/VSO proof.
`bootstrap_vault.py` is now plan-only; `--apply` cannot create another root engine
or credentials. `contract(canonical_dev=True)` renders the desired policy plan;
the default contract describes canonical dev readers and unchanged production
readers. `contract(canonical_dev=False)` is retained for rollback planning only.

## Phase 2 — not authorized until rollout verification

Only after explicit confirmation and auditing all active readers: soft-delete
unused **old dev** records and remove their old **dev-only** grants. Retain secret
history. Do not remove the `wallettracker` engine or shared records.

## Production/shared — plan only

The owner-specified production destinations are
`downops/apps/wallettracker/prod/{mobile,runtime,rsa,signing}`. Current production
readers still reference `downops/apps/wallettracker/{runtime,rsa,signing}` without
`prod/`; keep these old values until an approved production-reader cutover.
Do not mutate those source values or existing
`wallettracker/delivery/{harbor-ci,harbor-pull,gitops-read,github-mirror,argocd-prod}`.
`delivery/gitops-read` requires `SSH_PRIVATE_KEY`; `delivery/argocd-prod` requires
`TOKEN`. These global/production consumers are not changed by the dev cutover.
Inventory their readers and plan one unchanged-value move per shared record to
`downops/apps/wallettracker/delivery/<name>`. Production pull/repository/CI readers
and protected-main GitOps need a separately approved coordinated cutover; never
leave a live patch that Argo will revert. Do not duplicate shared values per env.
