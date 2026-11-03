"""Request the existing public webhook; never claim a deployment succeeded."""
import json
import os
import re
import urllib.error
import urllib.request


def main():
    if os.environ['SOURCE_BRANCH'] != 'main':
        raise RuntimeError('Production job accepts main only')
    revision = os.environ['SOURCE_REVISION']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise RuntimeError('Invalid source revision')
    request = urllib.request.Request(os.environ['JENKINS_WEBHOOK_URL'],
        data=json.dumps({'origin': os.environ.get('REQUEST_ORIGIN', 'github'), 'CORRELATION_ID': revision}).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0',
                 'token': os.environ['JENKINS_CD_SECRET']})
    # Never forward the webhook credential through an HTTP redirect.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            raise RuntimeError('Unexpected webhook redirect')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError('Jenkins webhook failed (HTTP %d)' % error.code) from None
    job = result.get('jobs', {}).get('wallettracker_cd')
    if not job or job.get('triggered') is not True:
        raise RuntimeError('Webhook did not trigger wallettracker_cd')
    print('Jenkins accepted the plan request for %s; verify its build result in internal Jenkins. No deployment success is implied.' % revision)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else 'Webhook request failed; diagnostics suppressed')
        raise SystemExit(1)
