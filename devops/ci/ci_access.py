"""Job-time, scoped JWT Vault reads and private HTTPS; no persistent fetcher."""
import http.client,json,os,socket,ssl,urllib.parse
def raw_request(url,method='GET',data=None,headers=None):
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.username or u.password:raise RuntimeError('Verified HTTPS required')
    class Connection(http.client.HTTPSConnection):
        def connect(self):
            address='10.2.0.10' if self.host in ['vault.int.downops.win','argocd.int.downops.win','wallettracker-dev.int.downops.win'] else self.host
            self.sock=self._context.wrap_socket(socket.create_connection((address,self.port or 443),timeout=30),server_hostname=self.host)
    c=Connection(u.hostname,u.port or 443,context=ssl.create_default_context(),timeout=30)
    try:
        c.request(method,u.path+('?' +u.query if u.query else ''),body=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0 WalletTracker-Delivery',**(headers or {})});r=c.getresponse();raw=r.read()
        if not 200<=r.status<300:raise RuntimeError('HTTPS request rejected (HTTP '+str(r.status)+'); response withheld')
        return raw,dict(r.getheaders())
    finally:c.close()
def request(url,method='GET',data=None,headers=None):
    raw,_=raw_request(url,method,data,headers);return json.loads(raw) if raw else {}
class Vault:
    def __init__(self,role):
        expected={'GITLAB_CI':'true','CI_PROJECT_ID':'1','CI_PROJECT_PATH':'downops/wallet-tracker-backend'}
        if any(os.environ.get(k)!=v for k,v in expected.items()):raise RuntimeError('Verified GitLab backend job identity required')
        if role not in ['wallettracker-ci-scan','wallettracker-ci-dev','wallettracker-ci-prod']:raise RuntimeError('Unknown scoped delivery role')
        if os.environ.get('CI_PIPELINE_SOURCE')=='merge_request_event':raise RuntimeError('Merge requests cannot obtain delivery credentials')
        jwt=os.environ.get('VAULT_ID_TOKEN')
        if not jwt:raise RuntimeError('A job-scoped GitLab OIDC token is required')
        self.token=request('https://vault.int.downops.win/v1/auth/gitlab-ci/login','POST',{'role':role,'jwt':jwt})['auth']['client_token']
    def read(self,path):
        return request('https://vault.int.downops.win/v1/'+path,headers={'X-Vault-Token':self.token})['data']['data']
