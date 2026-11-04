"""Publish immutable artifact, environment-only GitOps writeback, refresh, verify.

No kubeconfig, imperative application sync, estate-admin token or secret argv.
Git credential helpers return secrets only to native Git over its private pipe.
"""
import json,os,pathlib,re,subprocess,sys,tempfile,time
from ci_access import Vault,request,raw_request
IMAGE='registry.int.downops.win/wallettracker/backend';PUSH='registry.downops.win/wallettracker/backend'
def command(args,env=None,input=None):
    p=subprocess.run(args,input=input,capture_output=True,env=env)
    if p.returncode:raise RuntimeError('Delivery command failed: '+args[0]+'; credential-bearing diagnostics withheld')
    return p.stdout.decode().strip()
def main(env):
    if env not in ['dev','prod']:raise RuntimeError('Unknown environment')
    version=pathlib.Path('VERSION').read_text().strip();sha=os.environ['CI_COMMIT_SHA'];branch='dev' if env=='dev' else 'main'
    if not re.fullmatch(r'\d+\.\d+\.\d+',version) or not re.fullmatch('[a-f0-9]{40}',sha):raise RuntimeError('Invalid immutable version/revision')
    if env=='prod':
        if os.environ.get('CI_COMMIT_TAG')!='v'+version or os.environ.get('CI_COMMIT_REF_PROTECTED')!='true':raise RuntimeError('Protected versioned release tag required')
        command(['git','fetch','origin','main']);command(['git','merge-base','--is-ancestor',sha,'origin/main'])
    elif os.environ.get('CI_COMMIT_BRANCH')!='dev':raise RuntimeError('Dev publication must originate on dev')
    tag='dev-'+version+'-'+sha[:8] if env=='dev' else version;target=PUSH+':'+tag
    vault=Vault('wallettracker-ci-'+env);robot=vault.read('wallettracker/data/delivery/harbor-ci');mirror=vault.read('wallettracker/data/delivery/github-mirror');status=vault.read('wallettracker/data/delivery/argocd-'+env)['TOKEN']
    with tempfile.TemporaryDirectory(prefix='wallettracker-delivery-') as tmp:
        tmp=pathlib.Path(tmp);tmp.chmod(0o700);child=dict(os.environ,DOCKER_CONFIG=str(tmp/'docker'))
        command(['docker','login','registry.downops.win','--username',robot['HARBOR_ROBOT_NAME'],'--password-stdin'],child,robot['HARBOR_ROBOT_SECRET'].encode())
        exists=subprocess.run(['docker','manifest','inspect',target],env=child,capture_output=True).returncode==0
        if exists:
            command(['docker','pull',target],child)
            actual=json.loads(command(['docker','image','inspect',target],child))[0]['Config']['Labels'].get('org.opencontainers.image.revision')
            if actual!=sha:raise RuntimeError('Immutable release tag belongs to another source revision')
        else:
            command(['docker','build','--build-arg','BUILD_REVISION='+sha,'--label','org.opencontainers.image.revision='+sha,'--label','org.opencontainers.image.version='+version,'-t',target,'app'],child)
            command(['docker','push',target],child)
        ask=tmp/'askpass';ask.write_text('#!/usr/bin/env python3\nimport os,sys\nprint("gitlab-ci-token" if "username" in sys.argv[1].lower() else os.environ["CI_JOB_TOKEN"])\n');ask.chmod(0o700);child.update(GIT_ASKPASS=str(ask),GIT_TERMINAL_PROMPT='0')
        remote=os.environ['CI_SERVER_URL'].rstrip('/')+'/'+os.environ['CI_PROJECT_PATH']+'.git'
        command(['git','-c','credential.helper=','fetch',remote,branch],child);head=command(['git','rev-parse','FETCH_HEAD'])
        file=pathlib.Path('k8s')/env/'kustomization.yaml'
        if head!=sha:
            changed=set(command(['git','diff','--name-only',sha,head]).splitlines());current=json.loads(command(['git','show',head+':'+str(file)]))
            if changed-{str(file)} or current.get('images')!=[{'name':IMAGE,'newTag':tag}]:
                print('Source superseded; immutable image retained, no stale GitOps writeback performed');return
        command(['git','checkout','-B','gitops-writeback','FETCH_HEAD']);data=json.loads(file.read_text());revision=head
        if data.get('images')!=[{'name':IMAGE,'newTag':tag}]:
            data['images']=[{'name':IMAGE,'newTag':tag}];file.write_text(json.dumps(data,indent=2)+'\n')
            command(['git','config','user.name','WalletTracker GitOps CI']);command(['git','config','user.email','wallettracker-ci@downops.invalid']);command(['git','add',str(file)])
            command(['git','commit','-m','[gitops '+env+'] '+tag+' [skip ci]']);revision=command(['git','rev-parse','HEAD']);command(['git','-c','credential.helper=','push','-o','ci.skip',remote,'HEAD:'+branch],child)
        # Refresh always follows authoritative writeback, even if mirror push fails.
        request('https://argocd.int.downops.win/api/webhook','POST',{'object_kind':'push','ref':'refs/heads/'+branch,'project':{'web_url':'https://10.2.0.11/downops/wallet-tracker-backend'},'repository':{'url':'ssh://git@10.2.0.11:2222/downops/wallet-tracker-backend.git'}},{'X-Gitlab-Event':'Push Hook'})
        key=tmp/'github-key';known=tmp/'known_hosts';key.write_text(mirror['SSH_PRIVATE_KEY']);key.chmod(0o600);known.write_text(mirror['KNOWN_HOSTS']);known.chmod(0o600)
        child['GIT_SSH_COMMAND']='ssh -i '+str(key)+' -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile='+str(known)
        command(['git','push','git@github.com:noelnovo/WalletTrackerBackend.git','HEAD:'+branch],child)
        expected=IMAGE+':'+tag;app='wallettracker-'+env
        for _ in range(120):
            result=request('https://argocd.int.downops.win/api/v1/applications/'+app,headers={'Authorization':'Bearer '+status});state=result.get('status',{})
            if state.get('sync',{}).get('revision')==revision and state.get('sync',{}).get('status')=='Synced' and state.get('health',{}).get('status')=='Healthy' and expected in state.get('summary',{}).get('images',[]):
                host='api.downops.win' if env=='prod' else 'wallettracker-dev.int.downops.win'
                try:
                    raw,headers=raw_request('https://'+host+'/api/v1/ready')
                    revision_header=next((v for k,v in headers.items() if k.lower()=='x-wallettracker-revision'),None)
                    if json.loads(raw).get('success') and revision_header==sha:
                        print(json.dumps({'environment':env,'gitops_revision':revision,'image':expected,'argocd':'Synced/Healthy','actual_api_database_ready_on_built_revision':True}));return
                except RuntimeError:pass
            time.sleep(5)
        raise RuntimeError('Rollout verification timed out; production requires the approved manual Argo sync and restored-data gate')
if __name__=='__main__':
    try:main(sys.argv[1])
    except Exception as e:print(json.dumps({'delivery_failed':True,'error_class':type(e).__name__,'safe_error':str(e) if isinstance(e,RuntimeError) else 'details withheld'}));raise SystemExit(1)
