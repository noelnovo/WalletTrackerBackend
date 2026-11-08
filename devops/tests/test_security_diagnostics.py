import contextlib
import io
import unittest
from unittest.mock import patch
from devops.ci import security_diagnostics


class SafeSecurityDiagnosticsTests(unittest.TestCase):
    def test_annotations_escape_workflow_commands_and_remain_bounded(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            security_diagnostics.annotation('Gate', 'coverage\n::notice::unsafe% ' + 'x' * 2000)
        value = output.getvalue()
        self.assertIn('%0A::notice::unsafe%25', value)
        self.assertEqual(value.count('\n'), 1)
        self.assertLess(len(value), 1100)

    def test_gate_diagnostics_do_not_print_credentials(self):
        responses = [
            {'projectStatus': {'status': 'ERROR', 'conditions': [
                {'status': 'ERROR', 'metricKey': 'new_coverage', 'actualValue': '70', 'errorThreshold': '80', 'comparator': 'LT'}]}},
            {'issues': [{'rule': 'python:S3776', 'component': 'project:app/example.py', 'line': 10,
                         'message': 'Reduce complexity', 'type': 'CODE_SMELL', 'severity': 'CRITICAL'}]},
            {'hotspots': []},
        ]
        output = io.StringIO()
        values = {'SONAR_TOKEN': 'synthetic-credential-not-for-output', 'SONAR_HOST_URL': 'https://sonar.invalid'}
        with patch.object(security_diagnostics, 'request', side_effect=responses), contextlib.redirect_stdout(output):
            security_diagnostics.report(values)
        text = output.getvalue()
        self.assertIn('new_coverage: actual=70; required=80', text)
        self.assertIn('python:S3776', text)
        self.assertNotIn(values['SONAR_TOKEN'], text)
        self.assertNotIn('Authorization', text)


if __name__ == '__main__':
    unittest.main()
