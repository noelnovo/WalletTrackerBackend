"""Strict opt-in protected DEV auth-only proof. No renew/revoke, writes or artifacts.

CI-definition integration is NOT active until the parent's separately reviewed
proof-only pipeline boundary is published. This module never invokes a CI job.
"""
import http.client
import json
import os
import socket
import ssl
import sys
import time

READ_PATHS = [
    'downops/data/services/harbor/ci/instance-004',
    'downops/data/apps/wallettracker/delivery/harbor-ci',
    'downops/data/apps/wallettracker/delivery/github-mirror',
    'downops/data/apps/wallettracker/delivery/argocd-dev',
]
OLD_PATHS = ['wallettracker/data/' + path for path in [
    'dev/database', 'dev/rsa', 'dev/signing', 'delivery/harbor-ci', 'delivery/harbor-pull',
    'delivery/github-mirror', 'delivery/gitops-read', 'delivery/argocd-dev', 'delivery/argocd-prod',
]]
UNRELATED_PATHS = [
    'downops/data/apps/wallettracker/prod/runtime',
    'downops/data/services/opencode/server',
]


class ProofFailure(RuntimeError):
    pass


def require(ok):
    if not ok:
        raise ProofFailure('Proof prerequisite failed; response withheld')


class Transport:
    """Verified existing private HTTPS route; bounded, no redirects/raw output."""
    def __init__(self):
        self.deadline = time.monotonic() + 75

    def request(self, method, path, body=None, token=None):
        require((method == 'POST' and path == 'auth/gitlab-ci/login') or
                (method == 'GET' and path in READ_PATHS + OLD_PATHS + UNRELATED_PATHS +
                 ['auth/token/lookup-self']))
        remaining = min(10, self.deadline - time.monotonic())
        require(remaining > 0)
        class Connection(http.client.HTTPSConnection):
            def connect(self):
                self.sock = self._context.wrap_socket(
                    socket.create_connection(('10.2.0.10', 443), timeout=remaining),
                    server_hostname='vault.int.downops.win')
        connection = Connection('vault.int.downops.win', context=ssl.create_default_context(), timeout=remaining)
        try:
            headers = {'Content-Type': 'application/json', 'User-Agent': 'WalletTracker-Vault-Layout-Proof/1.0'}
            if token:
                headers['X-Vault-Token'] = token
            connection.request(method, '/v1/' + path,
                               body=None if body is None else json.dumps(body).encode(), headers=headers)
            response = connection.getresponse()
            raw = response.read(1024 * 1024 + 1)
            require(len(raw) <= 1024 * 1024)
            # Error/denial bodies are never parsed, returned, printed or persisted.
            payload = json.loads(raw) if response.status == 200 and raw else {}
            return response.status, payload
        finally:
            connection.close()


def context(env):
    expected = {'VAULT_LAYOUT_PROOF_ONLY': 'true', 'GITLAB_CI': 'true', 'CI_PROJECT_ID': '1',
                'CI_PROJECT_PATH': 'downops/wallet-tracker-backend', 'CI_COMMIT_BRANCH': 'dev',
                'CI_COMMIT_REF_NAME': 'dev', 'CI_COMMIT_REF_PROTECTED': 'true'}
    require(all(env.get(name) == value for name, value in expected.items()))
    require(env.get('CI_PIPELINE_SOURCE') in ('api', 'web'))
    require(bool(env.get('VAULT_ID_TOKEN')))


def proof(env, transport):
    context(env)
    code, payload = transport.request('POST', 'auth/gitlab-ci/login',
                                      {'role': 'wallettracker-ci-dev', 'jwt': env['VAULT_ID_TOKEN']})
    require(code == 200)
    auth = payload['auth']
    require(auth.get('token_type') == 'batch' and auth.get('renewable') is False and
            0 < auth.get('lease_duration', 0) <= 900 and
            auth.get('policies') == ['wallettracker-ci-dev'] and bool(auth.get('client_token')))
    token = auth['client_token']  # Job-local memory only; never argv/env/file/hash/output.
    try:
        code, payload = transport.request('GET', 'auth/token/lookup-self', token=token)
        require(code == 200 and payload['data'].get('type') == 'batch' and
                payload['data'].get('renewable') is False and
                payload['data'].get('policies') == ['wallettracker-ci-dev'] and
                0 < payload['data'].get('ttl', 0) <= 900)
        reads = {}
        for path in READ_PATHS:
            code, payload = transport.request('GET', path, token=token)
            require(code == 200 and isinstance(payload.get('data', {}).get('data'), dict))
            reads[path] = code
        old = {path: transport.request('GET', path, token=token)[0] for path in OLD_PATHS}
        unrelated = {path: transport.request('GET', path, token=token)[0] for path in UNRELATED_PATHS}
        report = {'authenticated': True, 'batch_token': True, 'canonical_reads_passed': True,
                  'lookup_status': 200, 'read_statuses': reads, 'old_statuses': old,
                  'unrelated_statuses': unrelated, 'writes_or_artifacts': False}
        if any(code != 403 for code in unrelated.values()):
            return 4, {**report, 'gate': 'UNRELATED_DENIAL_FAILED', 'retirement_ready': False}
        if any(code == 200 for code in old.values()):
            return 3, {**report, 'gate': 'OLD_GRANTS_STILL_PRESENT_NOT_A_READ_FAILURE', 'retirement_ready': False}
        if any(code != 403 for code in old.values()):
            return 3, {**report, 'gate': 'OLD_MOUNT_DENIAL_MUST_BE_403_BEFORE_DISABLE', 'retirement_ready': False}
        return 0, {**report, 'gate': 'AUTH_READ_DENIAL_PROOF_PASSED', 'retirement_ready': False}
    finally:
        # Batch tokens expire naturally: unsupported renewal/self-revoke is NOT attempted.
        token = None


def main(env=None, transport=None):
    try:
        code, report = proof(os.environ if env is None else env, transport or Transport())
    except BaseException as error:
        code, report = 2, {'gate': 'PROOF_ERROR', 'safe_error_type': type(error).__name__,
                          'retirement_ready': False}
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
