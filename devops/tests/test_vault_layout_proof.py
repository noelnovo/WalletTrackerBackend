"""Offline mock proof tests. No Vault/CI/job/image/runtime execution."""
import contextlib
import io
import json
import pathlib
import unittest
from devops.ci import vault_layout_proof as p

ROOT = pathlib.Path(__file__).resolve().parents[2]


def environment():
    return {'VAULT_LAYOUT_PROOF_ONLY':'true','GITLAB_CI':'true','CI_PROJECT_ID':'1',
            'CI_PROJECT_PATH':'downops/wallet-tracker-backend','CI_COMMIT_BRANCH':'dev',
            'CI_COMMIT_REF_NAME':'dev','CI_COMMIT_REF_PROTECTED':'true','CI_PIPELINE_SOURCE':'web',
            'VAULT_ID_TOKEN':'synthetic-jwt-not-for-output'}


class Fake:
    def __init__(self, old=403, unrelated=403):
        self.old,self.unrelated=old,unrelated
        self.calls=[]
        self.token_type='batch'
    def request(self, method, path, body=None, token=None):
        self.calls.append((method,path))
        if path=='auth/gitlab-ci/login':
            return 200,{'auth':{'client_token':'synthetic-token-not-for-output','token_type':self.token_type,
                       'renewable':False,'lease_duration':900,'policies':['wallettracker-ci-dev']}}
        if path=='auth/token/lookup-self':
            return 200,{'data':{'id':'synthetic-token-not-for-output','type':'batch','renewable':False,
                       'ttl':899,'policies':['wallettracker-ci-dev']}}
        if path in p.READ_PATHS:return 200,{'data':{'data':{'PRIVATE':'synthetic-payload-not-for-output'}}}
        return (self.old if path in p.OLD_PATHS else self.unrelated),{'PRIVATE':'synthetic-payload-not-for-output'}


class ProofTests(unittest.TestCase):
    def test_only_api_and_web_sources_accept_same_proof(self):
        for source in ['api', 'web']:
            env=environment();env['CI_PIPELINE_SOURCE']=source
            self.assertEqual(p.proof(env,Fake())[0],0)
        for source in ['push','schedule','trigger','parent_pipeline','pipeline','external','',None]:
            env=environment();env['CI_PIPELINE_SOURCE']=source;fake=Fake()
            with self.assertRaises(p.ProofFailure):p.proof(env,fake)
            self.assertEqual(fake.calls,[])
    def test_batch_reads_and_denials_pass_without_unsupported_calls(self):
        fake=Fake();code,report=p.proof(environment(),fake)
        self.assertEqual(code,0);self.assertTrue(report['canonical_reads_passed'])
        self.assertFalse(report['retirement_ready'])
        self.assertEqual(sum(method=='POST' for method,path in fake.calls),1)
        self.assertFalse(any('renew' in path or 'revoke' in path or 'sys/policies' in path for _,path in fake.calls))
    def test_old_grants_gate_is_not_read_failure(self):
        code,report=p.proof(environment(),Fake(old=200))
        self.assertEqual(code,3);self.assertTrue(report['canonical_reads_passed'])
        self.assertEqual(report['gate'],'OLD_GRANTS_STILL_PRESENT_NOT_A_READ_FAILURE')
    def test_old_404_not_denial_proof_and_unrelated_read_fails(self):
        self.assertEqual(p.proof(environment(),Fake(old=404))[0],3)
        self.assertEqual(p.proof(environment(),Fake(unrelated=200))[0],4)
    def test_context_is_opt_in_protected_dev_project_only(self):
        for key,value in [('VAULT_LAYOUT_PROOF_ONLY','false'),('CI_COMMIT_BRANCH','main'),
                          ('CI_COMMIT_REF_PROTECTED','false'),('CI_PIPELINE_SOURCE','merge_request_event'),
                          ('CI_PROJECT_ID','31')]:
            env=environment();env[key]=value;fake=Fake()
            with self.assertRaises(p.ProofFailure):p.proof(env,fake)
            self.assertEqual(fake.calls,[])
    def test_nonbatch_auth_not_accepted(self):
        fake=Fake();fake.token_type='service'
        with self.assertRaises(p.ProofFailure):p.proof(environment(),fake)
    def test_stdout_never_contains_payload_token_jwt_or_error_message(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertEqual(p.main(environment(),Fake(old=200)),3)
        for value in ['synthetic-token-not-for-output','synthetic-jwt-not-for-output','synthetic-payload-not-for-output']:
            self.assertNotIn(value,output.getvalue())
        class Broken:
            def request(self,*args,**kwargs):raise ValueError('synthetic-private-error-payload')
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertEqual(p.main(environment(),Broken()),2)
        self.assertNotIn('synthetic-private-error-payload',output.getvalue())
    def test_no_files_hashes_artifacts_or_process_invocation(self):
        source=(ROOT/'devops/ci/vault_layout_proof.py').read_text()
        for forbidden in ['hashlib','open(', 'subprocess', 'os.system', '::add-mask::']:
            self.assertNotIn(forbidden,source)
    def test_proposed_ci_boundary_excludes_all_ordinary_jobs_not_published(self):
        plan=json.loads((ROOT/'devops/config/vault-layout-proof-plan.json').read_text())
        proposed=plan['proposed_integration'];job=proposed['job_definition']
        self.assertTrue(proposed['review_required'])
        self.assertEqual(job['needs'],[]);self.assertEqual(job['services'],[])
        self.assertNotIn('artifacts',job)
        self.assertEqual(job['id_tokens']['VAULT_ID_TOKEN']['aud'],'https://vault.int.downops.win')
        normal={'delivery-tests','application-tests','image-smoke','security-gates','publish-dev','publish-prod'}
        self.assertEqual(set(proposed['ordinary_jobs_excluded']),normal)
        # Installed SOURCE definition; not a claim that it is published/invoked.
        installed=json.loads((ROOT/'.gitlab/vault-layout-proof.yml').read_text())
        self.assertEqual(installed[proposed['only_job_name']],job)
        self.assertFalse(set(installed) & normal)


if __name__=='__main__':unittest.main()
