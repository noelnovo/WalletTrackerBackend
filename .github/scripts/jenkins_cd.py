"""Supported Jenkins API only; never emit credentials or raw HTTP responses."""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request


def main():
    host = os.environ['JENKINS_HOSTNAME']
    if not re.fullmatch(r'[A-Za-z0-9.-]+', host):
        raise RuntimeError('Invalid Jenkins hostname')
    if os.environ['SOURCE_BRANCH'] != 'main':
        raise RuntimeError('Production job accepts main only')
    revision = os.environ['SOURCE_REVISION']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise RuntimeError('Invalid source revision')
    base = 'https://' + host
    credential = base64.b64encode((os.environ['JENKINS_USERNAME'] + ':' + os.environ['JENKINS_API_TOKEN']).encode()).decode()

    class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not newurl.startswith(base + '/'):
                raise RuntimeError('Refusing cross-origin Jenkins redirect')
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(SameOriginRedirect())

    def request(path, data=None):
        # Do not follow a queue URL to another origin with the Authorization header.
        url = urllib.parse.urljoin(base, path)
        if urllib.parse.urlsplit(url).netloc != host or not url.startswith(base + '/'):
            raise RuntimeError('Unexpected Jenkins URL')
        req = urllib.request.Request(url, data=data, headers={'Authorization': 'Basic ' + credential})
        try:
            return opener.open(req, timeout=30)
        except urllib.error.HTTPError as error:
            raise RuntimeError('Jenkins API request failed (HTTP %d)' % error.code) from None

    parameters = urllib.parse.urlencode({'GIT_BRANCH': 'main', 'SOURCE_REVISION': revision, 'APPLY': os.environ.get('APPLY', 'false')}).encode()
    with request('/job/wallettracker_cd/buildWithParameters', parameters) as response:
        queue = response.headers.get('Location')
    if not queue:
        raise RuntimeError('Jenkins did not return a queue item; deployment is not confirmed')
    deadline = time.monotonic() + 65 * 60
    build = None
    while time.monotonic() < deadline:
        with request(queue.rstrip('/') + '/api/json') as response:
            item = json.load(response)
        if item.get('cancelled'):
            raise RuntimeError('Jenkins queue item was cancelled')
        if item.get('executable'):
            build = item['executable']
            break
        time.sleep(5)
    if build is None:
        raise RuntimeError('Timed out waiting for Jenkins queue')
    print('Jenkins build #%d started for %s' % (build['number'], revision), flush=True)
    while time.monotonic() < deadline:
        with request(build['url'].rstrip('/') + '/api/json') as response:
            result = json.load(response)
        if not result.get('building') and result.get('result'):
            if result['result'] != 'SUCCESS':
                raise RuntimeError('Jenkins build #%d finished with %s' % (build['number'], result['result']))
            print('Jenkins build #%d succeeded (%s)' % (build['number'], 'approved deployment' if os.environ.get('APPLY') == 'true' else 'plan only; production unchanged'))
            return
        time.sleep(5)
    raise RuntimeError('Timed out waiting for Jenkins result; do not assume deployment success')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else 'Jenkins CD failed; diagnostics suppressed')
        raise SystemExit(1)
