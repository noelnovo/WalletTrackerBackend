import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import package_image


class ImagePackageTests(unittest.TestCase):
    def test_provenance_is_required_and_no_deployment_is_claimed(self):
        for outcome in ('valid', 'bad-labels', 'untrusted-pr'):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory(dir='/tmp/opencode') as directory:
                root=pathlib.Path(directory)
                (root/'VERSION').write_text('2.0.0\n')
                env={'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY_ID':'910129138',
                     'GITHUB_REPOSITORY_OWNER_ID':'128699907','GITHUB_SHA':'a'*40,
                     'GITHUB_EVENT_NAME':'pull_request' if outcome=='untrusted-pr' else 'push'}
                def command(args):
                    if args==['git','rev-parse','HEAD']:return 'a'*40
                    if args==['git','rev-parse','HEAD:app']:return 'b'*40
                    if args[:2]==['docker','save']:
                        pathlib.Path(args[-1]).write_bytes(b'synthetic-image');return ''
                    if '.Config.Labels' in args[4]:
                        return json.dumps({'org.opencontainers.image.revision':'c'*40 if outcome=='bad-labels' else 'a'*40,
                                           'org.opencontainers.image.version':'2.0.0'})
                    return 'sha256:'+'d'*64
                cwd=os.getcwd()
                try:
                    os.chdir(root)
                    with patch.dict(os.environ,env,clear=True),patch.object(package_image,'command',side_effect=command),patch('builtins.print'):
                        if outcome=='valid':package_image.main()
                        else:
                            with self.assertRaises(RuntimeError):package_image.main()
                finally:os.chdir(cwd)
                receipt=root/'delivery/artifacts/image-stage-receipt.json'
                if outcome=='valid':
                    value=json.loads(receipt.read_text())
                    self.assertEqual(value['source_revision'],'a'*40)
                    self.assertIs(value['production_deployed'],False)
                    self.assertIs(value['requires_security_and_recovery_proof_before_promotion'],True)
                else:self.assertFalse(receipt.exists())
