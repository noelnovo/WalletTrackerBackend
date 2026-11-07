"""Package a tested, secret-free GitHub-built image for reviewed registry promotion."""
import hashlib
import json
import os
import pathlib
import re
import subprocess


def command(args):
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError('Image packaging command failed; diagnostics withheld')
    return result.stdout.strip()


def main():
    expected = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY_ID': '910129138',
                'GITHUB_REPOSITORY_OWNER_ID': '128699907'}
    if any(os.environ.get(key) != value for key, value in expected.items()):
        raise RuntimeError('Only the approved GitHub backend workflow may package this image')
    if os.environ.get('GITHUB_EVENT_NAME') not in ('push', 'workflow_dispatch'):
        raise RuntimeError('Untrusted PR images cannot be staged for production')
    sha = os.environ.get('GITHUB_SHA', '')
    version = pathlib.Path('VERSION').read_text().strip()
    if not re.fullmatch('[a-f0-9]{40}', sha) or not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise RuntimeError('Invalid version/source identity')
    if command(['git', 'rev-parse', 'HEAD']) != sha:
        raise RuntimeError('Image source differs from the workflow checkout')
    labels = json.loads(command(['docker', 'image', 'inspect', '--format', '{{json .Config.Labels}}', 'wallettracker-ci']))
    if labels.get('org.opencontainers.image.revision') != sha or labels.get('org.opencontainers.image.version') != version:
        raise RuntimeError('Built image provenance label mismatch')
    output = pathlib.Path('delivery/artifacts')
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


if __name__ == '__main__':
    main()
