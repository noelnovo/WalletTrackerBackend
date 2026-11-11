"""Offline include isolation tests; GitLab remains the authoritative compiler.

The boundary uses JSON (a YAML subset) so its complete structure can be tested
with stdlib, without changing the normal job's image/install/before_script.
The normal include is opaque: byte equality plus a root with no overlay proves
that every workflow/rule/job/default/variable remains the same for each context.
"""
import hashlib
import itertools
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
NORMAL_SHA256 = 'f099c60388270a91fb75d53e0b6c4906a286e900470ccec6c40f72a52ef36073'


def evaluate(expression, env):
    """Interpret only the boundary's equality/AND/OR grammar; reject extensions."""
    tokens = re.findall(r'\$[A-Z_0-9]+|"[^"\\]*"|null|==|&&|\|\||[()]', expression)
    if ''.join(tokens) != re.sub(r'\s+', '', expression):
        raise AssertionError('Unsupported CI boundary expression')
    pos = 0

    def atom():
        nonlocal pos
        if tokens[pos] == '(':
            pos += 1
            value = either()
            assert tokens[pos] == ')'
            pos += 1
            return value
        variable, operator, literal = tokens[pos:pos+3]
        assert variable.startswith('$') and operator == '=='
        assert literal == 'null' or literal.startswith('"')
        pos += 3
        return env.get(variable[1:]) == (None if literal == 'null' else json.loads(literal))

    def both():
        nonlocal pos
        value = atom()
        while pos < len(tokens) and tokens[pos] == '&&':
            pos += 1
            right = atom()
            value = value and right
        return value

    def either():
        nonlocal pos
        value = both()
        while pos < len(tokens) and tokens[pos] == '||':
            pos += 1
            right = both()
            value = value or right
        return value

    result = either()
    assert pos == len(tokens)
    return result


def selected(rules, env):
    for rule in rules:
        if 'if' not in rule or evaluate(rule['if'], env):
            return rule.get('when', 'on_success') != 'never'
    return False


class ProofCI(unittest.TestCase):
    def setUp(self):
        self.root = json.loads((ROOT/'.gitlab-ci.yml').read_text())
        self.proof = json.loads((ROOT/'.gitlab/vault-layout-proof.yml').read_text())
        self.job = self.proof['vault-layout-auth-proof']

    def test_normal_bytes_and_root_has_no_merge_overlays(self):
        self.assertEqual(hashlib.sha256((ROOT/'.gitlab/ci.yml').read_bytes()).hexdigest(), NORMAL_SHA256)
        self.assertEqual(set(self.root), {'include'})
        self.assertEqual(len(self.root['include']), 2)
        for include in self.root['include']:
            self.assertEqual(set(include), {'local', 'rules'})
            self.assertEqual(len(include['rules']), 1)
            self.assertEqual(set(include['rules'][0]), {'if'})
        self.assertEqual([x['local'] for x in self.root['include']],
                         ['.gitlab/ci.yml', '.gitlab/vault-layout-proof.yml'])

    def test_full_context_matrix_cannot_mix_or_fallback(self):
        # None models absence; empty must preserve normal CI even on main/tags/MR.
        combinations = itertools.product(
            [None, '', 'true', 'false', 'TRUE', ' true', 'true ', '1'],
            ['1', '31'], ['downops', 'fork/downops'],
            ['dev', 'main', 'feature/proof', None], ['true', 'false', None],
            ['api', 'web', 'push', 'merge_request_event', 'schedule', 'trigger',
             'pipeline', 'parent_pipeline', 'external', None])
        for flag, project, namespace, branch, protected, source in combinations:
            env = dict(zip(['VAULT_LAYOUT_PROOF_ONLY', 'CI_PROJECT_ID',
                            'CI_PROJECT_NAMESPACE', 'CI_COMMIT_BRANCH',
                            'CI_COMMIT_REF_PROTECTED', 'CI_PIPELINE_SOURCE'],
                           [flag, project, namespace, branch, protected, source]))
            includes = [x['local'] for x in self.root['include'] if selected(x['rules'], env)]
            approved = (flag == 'true' and project == '1' and namespace == 'downops'
                        and branch == 'dev' and protected == 'true' and source in ('api', 'web'))
            expected = ['.gitlab/ci.yml'] if flag in (None, '') else (
                ['.gitlab/vault-layout-proof.yml'] if approved else [])
            self.assertEqual(includes, expected, env)
            self.assertEqual(selected(self.proof['workflow']['rules'], env), approved)
            self.assertEqual(selected(self.job['rules'], env), approved)

    def test_absent_empty_merged_normal_identity_for_all_existing_pipeline_cases(self):
        # The SAME bytes are supplied to GitLab, not a simplified rewritten normal
        # workflow. Thus even implicit MR exclusions/extends/needs stay identical.
        baseline = (ROOT/'.gitlab/ci.yml').read_bytes()
        for flag, source, branch, tag, message, open_mrs in itertools.product(
                [None, ''], ['push', 'merge_request_event', 'schedule', 'api', 'web'],
                ['dev', 'main', 'feature/x', None], [None, 'v2.1.0', 'other'],
                ['ordinary change', '[gitops dev] update'], [None, '17']):
            env = {'VAULT_LAYOUT_PROOF_ONLY': flag, 'CI_PIPELINE_SOURCE': source,
                   'CI_COMMIT_BRANCH': branch, 'CI_COMMIT_TAG': tag,
                   'CI_COMMIT_MESSAGE': message, 'CI_OPEN_MERGE_REQUESTS': open_mrs}
            merged_inputs = [(ROOT/x['local']).read_bytes() for x in self.root['include']
                             if selected(x['rules'], env)]
            self.assertEqual(merged_inputs, [baseline], env)

    def test_proof_merged_document_only_contains_one_manual_job(self):
        self.assertEqual(set(self.proof), {'stages', 'workflow', 'vault-layout-auth-proof'})
        self.assertEqual(self.proof['stages'], ['test'])
        self.assertEqual(self.job, {
            'stage': 'test', 'image': 'python:3.13-alpine', 'before_script': [],
            'after_script': [], 'needs': [], 'dependencies': [], 'services': [], 'cache': [],
            'interruptible': False, 'timeout': '2 minutes',
            'resource_group': 'wallettracker-vault-layout-proof',
            'id_tokens': {'VAULT_ID_TOKEN': {'aud': 'https://vault.int.downops.win'}},
            'rules': [dict(self.proof['workflow']['rules'][0], when='manual', allow_failure=False),
                      {'when': 'never'}],
            'script': ['python3 -m devops.ci.vault_layout_proof']})
        self.assertEqual(self.root['include'][1]['rules'][0], self.proof['workflow']['rules'][0])
        self.assertEqual(self.proof['workflow']['rules'][-1], {'when': 'never'})

    def test_plan_matches_installed_source_boundary(self):
        plan = json.loads((ROOT/'devops/config/vault-layout-proof-plan.json').read_text())
        self.assertEqual(plan['proposed_integration']['job_definition'], self.job)
        self.assertEqual(plan['ci_config_path'], '.gitlab-ci.yml')
        self.assertEqual(plan['normal_ci_sha256'], NORMAL_SHA256)
        self.assertEqual(plan['authorization']['job_invoke'], False)


if __name__ == '__main__':
    unittest.main()
