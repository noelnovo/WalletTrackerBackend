# Owner-requested cleanup and matching application layout

Run only after WalletTracker's GitHub migration, signing and delivery/cutover
proofs pass. Do not treat an untested consumer, skipped job or partial move as
permission to delete its source. Preserve production data and original identities.

## Requested grouping

- WalletTracker belongs under **downops** across the estate.
- Raju belongs in its **own project/group**.
- Vault secrets, Harbor images and GitLab backup projects should match as closely
  as each platform supports. GitHub remains the authoritative source/CI/APK host.
- Inventory other applications first; the owner's "etc" is not an approved
  per-application move list.

Current known WalletTracker sources:
- Vault canonical: `downops/apps/wallettracker/{dev,prod}/{runtime,rsa,signing,mobile}`
  and shared `downops/apps/wallettracker/delivery/`.
- Harbor current: project `wallettracker`, repository `backend`.
- GitLab backups: `downops/wallet-tracker-android` and `downops/wallet-tracker-backend`.

Candidate normalized targets for review, not yet executed:
- Harbor project `downops`, repository `wallettracker/backend`.
- GitLab group `downops`, subgroup `wallettracker`, projects `android` and `backend`.
- Keep the already-canonical WalletTracker Vault layout unless a reviewed map
  requires otherwise. Do not copy/rotate production credentials unnecessarily.
- Discover Raju's current sources/consumers and confirm its exact separate
  project/group and Vault prefix before changing anything.

## Required migration/retirement proof

1. Inventory source/destination paths, consumers, robot/project permissions,
   GitHub artifacts/caches/test refs and any remaining legacy CI scripts.
2. Resolve "GitHub blobs" into an exact cleanup list. Generated artifacts/cache
   are not the same as Git objects/history, LFS, published releases or production
   APK assets. No history rewrite or published-asset deletion without confirmation.
3. Copy images by verified digest before changing pull references. Preserve tags,
   signatures and rollback ability; update Git-tracked image paths, pull/CI scope,
   GitOps, backup remotes and documentation. Do not silently broaden robot access
   to unrelated apps because of Harbor's project-level RBAC.
4. Transfer/rename GitLab projects without losing IDs, branches, tags, protections
   or backup equality. Update every active URL, including any remaining Argo
   readers. No force push, broad deletion or unmanaged production patch.
5. Verify health, actual images/digests, CI/pull access, source/backup equality and
   canonical Vault consumers. Then retire only proven-unused namespaces, records,
   grants, test refs, generated artifacts and legacy scripts. Keep a nonsecret
   before/after receipt and list zero remaining active old references.
6. Preserve encrypted financial recovery proof and the installed APK signer.
   The build's previous-release APK baseline must remain available until replaced
   by a verified new baseline; published v2.2.2 is not automatically disposable.

No destructive cleanup, project move, image move, secret deletion or history
rewrite has been performed by this plan.
