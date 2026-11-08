"""Package the tested GitLab-built image without rebuilding for publication."""
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys


def command(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Image packaging command failed; diagnostics withheld')
    return result.stdout.strip()


def main():
    expected = {'GITLAB_CI': 'true', 'CI_PROJECT_ID': '1',
                'CI_PROJECT_PATH': 'downops/wallet-tracker-backend'}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Only the approved GitLab backend pipeline may package this image')
    if os.environ.get('CI_PIPELINE_SOURCE') == 'merge_request_event':
        raise RuntimeError('Untrusted merge request images cannot be staged for publication')
    sha = os.environ.get('CI_COMMIT_SHA', '')
    version = pathlib.Path('VERSION').read_text().strip()
    if not re.fullmatch('[a-f0-9]{40}', sha) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('Invalid version/source identity')
    if command(['git', 'rev-parse', 'HEAD']) != sha:
        raise RuntimeError('Image source differs from the workflow checkout')
    labels = json.loads(command(['docker', 'image', 'inspect', '--format', '{{json .Config.Labels}}', 'wallettracker-ci']))
    if labels.get('org.opencontainers.image.revision') != sha or labels.get('org.opencontainers.image.version') != version:
        raise RuntimeError('Built image provenance label mismatch')
    output = pathlib.Path('devops/artifacts')
    output.mkdir(parents=True, exist_ok=True)
    archive = output / 'backend-image.tar'
    command(['docker', 'save', 'wallettracker-ci', '-o', str(archive)])
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    receipt = {'source_revision': sha, 'version': version,
               'app_tree': command(['git', 'rev-parse', 'HEAD:app']),
               'image_id': command(['docker', 'image', 'inspect', '--format', '{{.Id}}', 'wallettracker-ci']),
               'archive_sha256': digest, 'production_deployed': False,
               'requires_security_and_recovery_proof_before_promotion': True}
    (output / 'image-stage-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print('Tested backend image packaged; registry promotion and deployment remain gated')


def verify():
    output = pathlib.Path('devops/artifacts')
    receipt = json.loads((output / 'image-stage-receipt.json').read_text())
    with (output / 'backend-image.tar').open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if (receipt['archive_sha256'] != digest
            or receipt['source_revision'] != os.environ.get('CI_COMMIT_SHA')
            or receipt['version'] != pathlib.Path('VERSION').read_text().strip()
            or receipt['app_tree'] != command(['git', 'rev-parse', 'HEAD:app'])):
        raise RuntimeError('Tested image artifact integrity/source mismatch')
    return receipt


if __name__ == '__main__':
    verify() if sys.argv[1:] == ['--verify'] else main()
