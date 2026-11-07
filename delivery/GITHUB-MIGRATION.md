# GitHub is authoritative; GitLab is backup only

`.github/workflows/backend.yml` owns backend delivery-contract checks, real
MariaDB migrations/application tests, image smoke and the real security gate.
GitLab CI is globally disabled and `.gitlab-ci.yml` has `when: never`. Old
GitLab job definitions are removed; do not run the legacy `publish.py` from
GitHub or treat an unported delivery path as passed.

The security job now performs real OIDC/DT/Sonar checks rather than failing at
a bootstrap boolean. It remains closed on any authentication or analysis error.
Trusted image-smoke runs package a secret-free, provenance-labelled Docker image
artifact for reviewed server-side registry promotion; PR artifacts cannot be
packaged for deployment. No registry credential is exported into GitHub for this
manual promotion path, and no image artifact may be promoted before all gates
and fresh financial recovery proof pass.

The exact new security OIDC role is in `github-actions-vault-plan.json`.
An already-authorized administrator must configure it without changing unrelated
trust or granting operator escalation. Until role/network verification,
`github-actions-status.json` keeps security/delivery readiness false. The required
`sonarqube` gate fails closed, rather than silently accepting missing analysis.
Untrusted PRs receive no scan/signing/production credentials.

GitHub MAIN's existing `python-tests`/`sonarqube` ruleset is preserved. CI-only
MAIN retirement changed no app/k8s content. This is not application promotion.

## Remaining backend delivery cutover

- Port immutable-image GitHub writeback with job-scoped `GITHUB_TOKEN` while
  respecting MAIN's existing rules and owner-reviewed production promotion.
- Move Argo app sources and AppProject allowlists to public GitHub HTTPS through
  reviewed GitOps; no new repository-read secret is needed for public repos.
- Verify public/hosted-runner reachability for the existing Sonar, DT, registry,
  Argo and dev-readiness endpoints; do not publish private services or weaken TLS.
- Preserve DEV behavior and manual PROD sync, fresh encrypted backup/restore,
  write-freeze/checkpoint/data-preservation and API-v2 cutover requirements.
- Retain old repository VSS/records/grants until new readers are verified and
  retirement is explicitly approved. No credential/key rotations.

## Passive repository backups

GitLab CE has no native pull mirroring. The existing authorized server writer
can fetch public GitHub and push only explicit fast-forward MAIN/DEV/tag backups
to GitLab. No force, deletion, `git push --mirror`, CI execution or estate-token
export is allowed. Backup automation must not be confused with the separately
approved one-off encrypted financial-database recovery checkpoint.
