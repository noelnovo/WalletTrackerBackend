# Development API v2 — exposure, data and security

Vault record purposes, the canonical prefix and the existing shared-reader
migration boundary are documented in [VAULT-LAYOUT.md](VAULT-LAYOUT.md).

## Observed exposure (2026-11-05)

- Internal resolution: `wallettracker-dev.int.downops.win -> 10.2.0.10`.
- Public Google DNS: NXDOMAIN for that hostname.
- Live Nginx Proxy Manager guest113 config `proxy_host/34.conf`: TLS/forced
  HTTPS for that hostname, forwarding HTTP to `10.2.0.100:31410`.
- Repo declaration: `wallettracker-dev/wallettracker-api` NodePort31410,
  externalTrafficPolicy Local, default-deny policies and explicit API sources.
- Production `api.downops.win` resolves to Cloudflare. The existing cutover
  receipt records the **shared** k3s Cloudflare connector as its owner, not a
  per-application Deployment in this repo. Do not deploy a duplicate connector
  or put its shared tunnel token into this application's secret scope.

**Network access is controlled by the existing router firewall.** The owner
confirmed that traffic from `192.168.1.0/24` to `10.2.0.0/24` is denied by default,
with a specific exception for the phone. The temporary backend LAN allowlist is
removed: the API does not duplicate that network policy or allow the whole home
LAN. Router rules, Nginx configuration and Kubernetes NetworkPolicies are unchanged.

`WALLET_TRACKER_TRUSTED_PROXIES=10.2.0.10/32` remains only to identify clients
behind NPM for rate limiting; it is not an IP access rule. Forwarded IPs supplied
by other peers are ignored. Authentication and the dev v1-write guard remain.

Private DNS alone is not an access-control boundary. We did not independently
audit the router firewall/NAT, perform an off-LAN probe or query the live shared
tunnel configuration. The firewall boundary above is owner-confirmed, not an
independent external-reachability proof. Production is unchanged.

## V2 contract

All v2 routes are JSON over verified client-facing TLS; no shared mobile secret,
RSA exchange, custom request signing or hybrid payload encryption is required.

| Route | Contract |
| --- | --- |
| `POST /api/v2/register` | Dev opt-in only; default disabled, username3–128, password12–1024 |
| `POST /api/v2/login` | Generic auth errors, five-minute access JWT, opaque refresh token |
| `POST /api/v2/refresh` | Single-use opaque token, session-locked rotation, replay revokes family |
| `POST /api/v2/logout` | Revokes session; access JWTs checked against revocation on every call |
| `GET /api/v2/sync?cursor=0&limit=100` | At most200 records/page, ordered committed tenant revision cursor |
| `POST /api/v2/sync` | At most100 mutations; UUID identity, expected base_version, durable receipt |

Refresh grants are stored as SHA-256 digests, not bearer plaintext. JWT
issuer/audience/type/required claims are verified; v1 tokens cannot authenticate
v2 requests. Database-backed throttles cover both protocol versions and all
workers: login10/5min, registration3/hour, refresh30/5min per trusted client IP.
Database failure fails authentication closed. These limits are a baseline, not
a replacement for edge DDoS controls or account-level abuse monitoring.

Password PBKDF2-SHA256 now uses600,000 iterations for new hashes; legacy100,000
hashes are upgraded after successful verification. Comparisons are constant-time.
User response serialization is allowlisted to id/username, never password hash,
salt, SQL credentials or private keys. SQL exception parameters are no longer
logged by the legacy response helper.

## Per-user storage and concurrency

The main database holds users/sessions/throttles; each user's existing separate
tenant database holds `SyncClock`, `SyncRecord`, `SyncReceipt` and legacy tables.
The tenant clock row serializes commits, including concurrent same-version
updates. Mismatches return explicit remote versions; clients must ask the user.
Money uses integer minor units. Category references and bill participants/payer
are validated. Optional bill `extras` contain an optional `description` (at most
80 characters), positive integer `amount_minor` and a `participant` from the
bill's unique names. At most 100 extras are allowed and their sum cannot exceed
the bill total. The remaining amount is divided equally with deterministic
remainder cents, then each person's assigned extras are added. Client-supplied
`shares` are ignored and recomputed; extras are retained across sync. Older
bills without extras remain equal splits. Deploy this validator before releasing
the paired itemized-bill Android UI; no schema migration is needed.
Deletion writes tombstones, not physical row deletion. Keep receipts/tombstones
until a reviewed device-watermark retention protocol exists.

Migration `d2a100000001` adds auth tables and matches the actual User FK type;
`d2b100000001` adds finance sync tables and copies existing categories/expenses
with deterministic UUIDs and decimal-to-cents conversion. Neither removes
legacy data. Dev sets `WALLET_TRACKER_V2_ONLY=true` so legacy writers cannot
diverge from the v2 copy. Migration checks refuse destructive downgrades.
Legacy income/statement data is retained, not silently deleted or represented
as expenses. No legacy device-only account attribution is guessed.

Tenant passwords are generated with32 random bytes; tenant connection URLs use
structured SQLAlchemy URLs and a bounded per-worker LRU pool. Tenant credentials
remain server-side; existing main-DB tenant passwords and legacy RSA columns are
**not yet envelope-encrypted at rest**, and the existing runtime still has SQL
provisioning/root authority. Separating provisioner/runtime privileges and a
Vault-backed envelope-key migration are remaining backend hardening work, not
claimed complete. No production password/key rotations are performed here.

## Release boundary and recovery

Only `dev` is changed. `k8s/prod`, production state/checkpoints and production
data are not modified. The existing dev GitLab/Harbor/Argo flow remains in use;
pipeline logic moves to `.gitlab/ci/pipeline.yml` with a minimal root include.
The new Android release must not be sent to production until legacy mobile-data
migration, real biometric UX, backend least-privilege and full release acceptance
are reviewed. Existing owner policy forbids new application backup schedules;
this work does not create one. Production migration requires an approved
off-cluster recovery plan, not an assumption that Vault contains finance data.

## Tests

Application tests cover pagination, conflict/retry/tombstone semantics, exact
bill cents, refresh replay/logout, malformed input, rate limits and forwarded-IP
spoofing protection for rate-limit identity. `delivery/v2_mariadb_smoke.py`, invoked by the real migration
job, also exercises actual MariaDB concurrency, distinct tenant isolation and
concurrent refresh reuse. It refuses non-CI or non-`*_ci` databases.
