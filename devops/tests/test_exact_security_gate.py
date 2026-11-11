"""Synthetic exact-analysis verification; no service credentials or requests."""
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from devops.ci import security_scan as subject


class ExactGateTests(unittest.TestCase):
    def test_release_mr_can_validate_the_current_gitops_writeback_tip(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        workflow=(root/'.gitlab/ci.yml').read_text().split('default:',1)[0]
        self.assertLess(workflow.index('merge_request_event'),workflow.index('CI_COMMIT_MESSAGE'))
        self.assertIn('when: never',workflow.split('CI_COMMIT_MESSAGE',1)[1])
        publisher=(root/'devops/ci/publish.py').read_text()
        commit=next(line for line in publisher.splitlines() if "command(['git','commit'" in line)
        self.assertNotIn('[skip ci]',commit)
        self.assertIn("'push','-o','ci.skip'",commit)

    def test_check_tags_scan_but_do_not_authorize_production_publication(self):
        root=pathlib.Path(__file__).resolve().parents[2]
        ci=(root/'.gitlab/ci.yml').read_text()
        self.assertIn('-ci-check',ci.split('security-gates:',1)[1].split('publish-dev:',1)[0])
        self.assertNotIn('-ci-check',ci.split('publish-prod:',1)[1])
        self.assertNotIn('map(select(.type',ci)
        self.assertIn("'--entrypoint','sonar-scanner'",(root/'devops/ci/security_scan.py').read_text())

    def test_exact_project_all_dt_conditions_and_current_analysis_required(self):
        creds={'SONAR_TOKEN':'synthetic-only','SONAR_HOST_URL':'https://example.invalid','SONAR_PROJECT_KEY':'synthetic-project'}
        wanted={'metric':'dependencytrack_fixed_high','op':'GT','error':'0'}
        valid={'metricKey':wanted['metric'],'comparator':'GT','errorThreshold':'0','actualValue':'0','status':'OK'}
        responses=[{'task':{'status':'SUCCESS','componentKey':'synthetic-project','analysisId':'exact-analysis'}},
                   {'qualityGate':{'name':'synthetic-gate'}},{'conditions':[wanted]},
                   {'projectStatus':{'status':'OK','conditions':[valid]}}]
        with tempfile.TemporaryDirectory() as directory:
            report=pathlib.Path(directory)/'report-task.txt';report.write_text('ceTaskId=exact-task\n')
            with patch.object(subject,'request',side_effect=responses) as call:
                subject.verify_exact_gate(creds,report)
                self.assertIn('analysisId=exact-analysis',call.call_args.args[0])
            # The existing canonical backend record has only host URL/token;
            # resolve the non-secret project key from the pinned source mapping.
            with patch.object(subject,'PROJECT_KEY','synthetic-project'),patch.object(subject,'request',side_effect=responses):
                subject.verify_exact_gate({k:v for k,v in creds.items() if k!='SONAR_PROJECT_KEY'},report)
            for bad in [{},dict(valid,status='ERROR'),dict(valid,actualValue='NaN'),dict(valid,errorThreshold='1')]:
                changed=responses[:-1]+[{'projectStatus':{'status':'OK','conditions':[bad] if bad else []}}]
                with patch.object(subject,'request',side_effect=changed),self.assertRaises(RuntimeError):
                    subject.verify_exact_gate(creds,report)
            changed=[{'task':{'status':'SUCCESS','componentKey':'unrelated-project','analysisId':'other'}}]
            with patch.object(subject,'request',side_effect=changed),self.assertRaises(RuntimeError):
                subject.verify_exact_gate(creds,report)


if __name__=='__main__':unittest.main()
