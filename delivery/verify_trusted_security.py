"""Analysis-credential-free PR gate backed by exact-source trusted security analysis."""
import json
import os
import pathlib
import re
import time
import urllib.request
import urllib.error

REPOSITORY = 'noelnovo/WalletTrackerBackend'
WORKFLOW = '.github/workflows/backend.yml'


def trusted(run, sha):
    return (
        run.get('head_sha') == sha
        and run.get('status') == 'completed'
        and run.get('conclusion') == 'success'
        and run.get('event') in ('push', 'workflow_dispatch')
        and run.get('head_branch') in ('dev', 'main')
        and run.get('path') == WORKFLOW
        and run.get('head_repository', {}).get('full_name') == REPOSITORY
    )


def api(path):
    # Use only the built-in actions:read job token. Anonymous runner traffic can
    # be rate-limited and must not be mistaken for a failed Sonar analysis.
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        raise RuntimeError('Built-in read-only GitHub evidence token is missing')
    request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + path,
                                     headers={'Accept': 'application/vnd.github+json',
                                              'User-Agent': 'WalletTracker-Exact-Source-Security-Gate',
                                              'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        raise RuntimeError(f'GitHub CI evidence request failed with HTTP {status}; verify actions:read access and rate limits') from None
    except urllib.error.URLError:
        raise RuntimeError('GitHub CI evidence network request failed; no scan result was accepted') from None


def wait_for_trusted_run(sha):
    # PR and trusted push jobs start concurrently. Wait for the real scan, not
    # for a guessed delay, and keep failure/absence fail-closed after 15 minutes.
    for attempt in range(21):
        runs = api('/actions/runs?head_sha=' + sha + '&per_page=30')['workflow_runs']
        evidence = next((run for run in runs if trusted(run, sha)), None)
        if evidence is not None:
            return evidence
        if attempt < 20:
            time.sleep(45)
    raise RuntimeError('A successful trusted DEV/MAIN security run for this exact PR source is required')


def main():
    if os.environ.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise RuntimeError('Unexpected repository identity')
    if os.environ.get('APPLICATION_RESULT') != 'success' or os.environ.get('IMAGE_RESULT') != 'success':
        raise RuntimeError('Application and image checks must pass')
    if os.environ.get('GITHUB_EVENT_NAME') != 'pull_request':
        if os.environ.get('SECURITY_RESULT') != 'success':
            raise RuntimeError('The full security analysis must pass')
        print(json.dumps({'full_security_analysis_passed': True}))
        return
    event = json.loads(pathlib.Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    sha = event['pull_request']['head']['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise RuntimeError('An exact source revision is required')
    evidence = wait_for_trusted_run(sha)
    jobs = api('/actions/runs/' + str(evidence['id']) + '/jobs?per_page=30')['jobs']
    checks = {job['name']: job.get('conclusion') for job in jobs}
    if any(checks.get(name) != 'success' for name in ('python-tests', 'delivery-tests', 'image-smoke')):
        raise RuntimeError('Trusted application/image/delivery evidence is incomplete')
    # Support the preceding workflow while transitioning to the dedicated scan job.
    if checks.get('security-analysis', checks.get('sonarqube')) != 'success':
        raise RuntimeError('Trusted Sonar/Dependency-Track analysis must pass')
    print(json.dumps({'exact_source_trusted_security_verified': True, 'source_revision': sha,
                      'trusted_run_id': evidence['id'], 'trusted_run_url': evidence['html_url'],
                      'pr_analysis_credentials_used': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('::error title=Exact-source security gate::' +
              (str(error) if isinstance(error, RuntimeError) else 'Evidence could not be verified; fail closed'))
        raise SystemExit(1)
