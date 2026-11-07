## WalletTracker backend 2.1.0

- API-v2 bill splitting supports individually assigned extras with optional descriptions.
- The bill total minus extras is shared equally, including deterministic remainder cents; each person's extras are then added to their share.
- Shares are recomputed server-side. Client-provided shares are not trusted.
- Extra owners, integer-cent prices, duplicate names, counts and total limits are validated before committing records.
- Extras survive sync retries and pull responses. Existing bills without extras remain equal splits.

No database schema migration, data reset, account change or key rotation is
required. Publish only the verified immutable CI image for this exact release
source. Reconcile GitHub/GitLab metadata history without discarding either side,
retain existing protections, and use the authorized Deployment-only production
promotion path. Do not replay the retired publisher or old v1→v2 migration hooks.

This backend capability is required before publishing Android WalletTracker 3.1.0
with itemized split-bill entry.
