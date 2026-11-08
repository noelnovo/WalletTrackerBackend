"""Read-only, credential-free Sonar gate diagnostics using the existing scoped CI role."""
import base64
import json
import pathlib
from urllib.parse import urlencode
from devops.ci.ci_access import Vault, request


def annotation(title, message):
    """Surface bounded, non-secret diagnostics in the check UI; never waive the gate."""
    def escape(value):
        return str(value)[:1000].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::error title=' + escape(title) + '::' + escape(message), flush=True)


def report(values):
    project = next(line.split('=', 1)[1] for line in pathlib.Path('sonar-project.properties').read_text().splitlines() if line.startswith('sonar.projectKey='))
    headers = {'Authorization': 'Basic ' + base64.b64encode((values['SONAR_TOKEN'] + ':').encode()).decode()}
    url = values['SONAR_HOST_URL'].rstrip('/')
    status = request(url + '/api/qualitygates/project_status?' + urlencode({'projectKey': project}), headers=headers)['projectStatus']
    print(json.dumps({'quality_gate': status['status'], 'conditions': status.get('conditions', [])}), flush=True)
    if status['status'] != 'OK':
        for condition in status.get('conditions', []):
            if condition.get('status') == 'ERROR':
                annotation('Sonar quality gate', '{metric}: actual={actual}; required={threshold}; comparator={comparison}'.format(
                    metric=condition.get('metricKey'), actual=condition.get('actualValue'),
                    threshold=condition.get('errorThreshold'), comparison=condition.get('comparator')))
    issues = request(url + '/api/issues/search?' + urlencode({'componentKeys': project, 'resolved': 'false', 'inNewCodePeriod': 'true', 'ps': 100}), headers=headers)
    for issue in issues.get('issues', []):
        print(json.dumps({key: issue.get(key) for key in ('rule', 'message', 'component', 'line', 'type', 'severity')}), flush=True)
        annotation('Sonar source finding', '{rule}: {component}:{line}: {message}'.format(
            rule=issue.get('rule'), component=issue.get('component'), line=issue.get('line'), message=issue.get('message')))
    try:
        hotspots = request(url + '/api/hotspots/search?' + urlencode({'projectKey': project, 'status': 'TO_REVIEW', 'ps': 100}), headers=headers)
    except RuntimeError:
        # Analysis-scoped identities may browse issues without hotspot-review authority.
        print(json.dumps({'hotspot_details': 'not permitted for this read-only diagnostic identity'}), flush=True)
        return
    for hotspot in hotspots.get('hotspots', []):
        print(json.dumps({'hotspot': hotspot.get('key'), 'message': hotspot.get('message'), 'component': hotspot.get('component'), 'line': hotspot.get('line')}), flush=True)


if __name__ == '__main__':
    try:
        report(Vault('wallettracker-ci-scan').read('downops/data/services/sonarqube/clients/instance-001'))
    except Exception as error:
        print(json.dumps({'diagnostics_unavailable': type(error).__name__}))
        raise SystemExit(1)
