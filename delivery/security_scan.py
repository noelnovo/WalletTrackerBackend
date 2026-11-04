"""Preserve real DT/Sonar gates using scoped job identity, no secret argv/logs."""
import base64,json,os,pathlib,subprocess,time
from ci_access import Vault,request
def main():
    vault=Vault('wallettracker-ci-scan');dt=vault.read('downops/data/services/dependency-track/clients/instance-001');sonar=vault.read('downops/data/services/sonarqube/clients/instance-001')
    headers={'X-Api-Key':dt['DT_API_KEY']};url=dt['DT_URL'].rstrip('/')
    result=request(url+'/api/v1/bom','PUT',{'project':dt['DT_PROJECT_UUID'],'bom':base64.b64encode(pathlib.Path('bom.json').read_bytes()).decode()},headers)
    token=result['token']
    for _ in range(120):
        value=request(url+'/api/v1/bom/token/'+token,headers=headers)
        if value.get('processing') is False:break
        time.sleep(5)
    else:raise RuntimeError('Dependency-Track analysis timed out')
    env=dict(os.environ,SONAR_TOKEN=sonar['SONAR_TOKEN'],SONAR_HOST_URL=sonar['SONAR_HOST_URL'])
    cmd=['docker','run','--rm','--env','SONAR_TOKEN','--env','SONAR_HOST_URL','--volume',os.getcwd()+':/usr/src','sonarsource/sonar-scanner-cli:latest','-Dsonar.qualitygate.wait=true','-Dsonar.qualitygate.timeout=300']
    p=subprocess.run(cmd,capture_output=True,env=env)
    if p.returncode:raise RuntimeError('SonarQube analysis/quality gate failed; diagnostics withheld')
    print(json.dumps({'dependency_track_analyzed':True,'sonarqube_quality_gate_passed':True}))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'security_gate_failed':True,'error_class':type(e).__name__,'safe_error':str(e) if isinstance(e,RuntimeError) else 'details withheld'}));raise SystemExit(1)
