"""Preserve real DT/Sonar gates using scoped job identity, no secret argv/logs."""
import base64,json,os,pathlib,subprocess,time,urllib.parse
from devops.ci.ci_access import Vault,request
def main():
    vault=Vault('wallettracker-ci-scan');dt=vault.read('downops/data/services/dependency-track/clients/instance-001');sonar=vault.read('downops/data/services/sonarqube/clients/instance-001')
    headers={'X-Api-Key':dt['DT_API_KEY']};url=dt['DT_URL'].rstrip('/')
    result=request(url+'/api/v1/bom','PUT',{'project':dt['DT_PROJECT_UUID'],'bom':base64.b64encode(pathlib.Path('bom.json').read_bytes()).decode()},headers)
    token=result['token']
    for _ in range(120):
        value=request(url+'/api/v1/event/token/'+token,headers=headers)
        if value.get('processing') is False:break
        if value.get('processing') is not True:raise RuntimeError('Invalid Dependency-Track processing state')
        time.sleep(5)
    else:raise RuntimeError('Dependency-Track analysis timed out')
    env=dict(os.environ,SONAR_TOKEN=sonar['SONAR_TOKEN'],SONAR_HOST_URL=sonar['SONAR_HOST_URL'])
    report=pathlib.Path('.scannerwork/report-task.txt');report.unlink(missing_ok=True)
    cmd=['docker','run','--rm','--entrypoint','sonar-scanner','--env','SONAR_TOKEN','--env','SONAR_HOST_URL','--volume',os.getcwd()+':/usr/src','sonarsource/sonar-scanner-cli@sha256:38207bba3d98c8ce6f6c051ea2b9f05a24480da78c9ee5945ceafc3d9de02b88','-Dsonar.qualitygate.wait=true','-Dsonar.qualitygate.timeout=300']
    p=subprocess.run(cmd,capture_output=True,env=env,timeout=600)
    if p.returncode:
        from devops.ci.security_diagnostics import report
        try:report(sonar)
        except Exception as error:print(json.dumps({'diagnostics_unavailable':type(error).__name__}))
        output=(p.stdout+p.stderr).decode(errors='replace').lower()
        # Emit fixed categories only: scanner output can include credentials.
        hints={name:needle in output for name,needle in {
            'quality_gate_rejected':'quality gate status: failed',
            'unauthorized':'not authorized',
            'authentication_failure':'authentication failed',
            'project_missing':'project not found',
            'permission_denied':'permission denied',
            'network_failure':'failed to connect',
            'dns_failure':'unknownhostexception',
            'tls_failure':'sslhandshakeexception',
            'coverage_path_failure':'cannot resolve',
            'workdir_failure':'unable to create',
            'analysis_submitted':'analysis report uploaded',
            'invalid_source_path':'does not exist',
            'oom':'outofmemoryerror',
        }.items()}
        print(json.dumps({'sonarqube_failure_categories':hints,'scanner_exit_code':p.returncode}))
        print('::error title=Sonar scanner failure categories::' + ', '.join(name for name, matched in hints.items() if matched), flush=True)
        raise RuntimeError('SonarQube analysis/quality gate failed; diagnostics withheld')
    verify_exact_gate(sonar,report)
    print(json.dumps({'dependency_track_analyzed':True,'sonarqube_quality_gate_passed':True}))


def verify_exact_gate(sonar,report):
    """Never accept cached OK or silently absent overall/new DT metrics."""
    base=sonar['SONAR_HOST_URL'].rstrip('/')
    headers={'Authorization':'Basic '+base64.b64encode((sonar['SONAR_TOKEN']+':').encode()).decode()}
    query=lambda path,values:request(base+path+'?'+urllib.parse.urlencode(values),headers=headers)
    task_values=dict(line.split('=',1) for line in report.read_text().splitlines() if '=' in line)
    task=query('/api/ce/task',{'id':task_values['ceTaskId']})['task']
    if task.get('status')!='SUCCESS' or task.get('componentKey')!=sonar['SONAR_PROJECT_KEY']:
        raise RuntimeError('Exact candidate analysis is incomplete or belongs to another project')
    assigned=query('/api/qualitygates/get_by_project',{'project':sonar['SONAR_PROJECT_KEY']})['qualityGate']
    configured=query('/api/qualitygates/show',{'name':assigned['name']})['conditions']
    expected=[c for c in configured if c['metric'].startswith(('dependencytrack_','new_dependencytrack_'))]
    actual=query('/api/qualitygates/project_status',{'analysisId':task['analysisId']})['projectStatus']
    conditions={c['metricKey']:c for c in actual['conditions']}
    if actual['status']!='OK' or not expected:raise RuntimeError('Configured quality gate rejected candidate')
    from decimal import Decimal
    for wanted in expected:
        value=conditions.get(wanted['metric'])
        if (not value or value['status']!='OK' or value.get('comparator')!=wanted['op']
                or Decimal(value['errorThreshold'])!=Decimal(wanted['error'])
                or not Decimal(value['actualValue']).is_finite()):
            raise RuntimeError('A configured Dependency-Track condition was absent, changed or failed')
    print(json.dumps({'exact_analysis_id':task['analysisId'],'configured_dt_conditions_evaluated':len(expected),
                      'gate_conditions':[{k:c[k] for k in ['metricKey','actualValue','errorThreshold','status']} for c in actual['conditions']]}))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'security_gate_failed':True,'error_class':type(e).__name__,'safe_error':str(e) if isinstance(e,RuntimeError) else 'details withheld'}));raise SystemExit(1)
