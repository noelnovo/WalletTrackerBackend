"""Deterministic non-secret GitOps declarations. Does not contact a cluster/Vault."""
import argparse,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[1]
IMAGE='registry.int.downops.win/wallettracker/backend'
CTRL='vault-secrets-operator-controller-manager'
def obj(kind,name,ns,spec=None,api='v1',**extra):
    result={'apiVersion':api,'kind':kind,'metadata':{'name':name,'namespace':ns}}
    if spec is not None:result['spec']=spec
    result.update(extra);return result
def auth(name,ns):
    return [obj('ServiceAccount',name,ns,automountServiceAccountToken=False),obj('VaultAuth',name,ns,{'vaultConnectionRef':'vault-secrets-operator/default','method':'jwt','mount':'jwt','jwt':{'role':ns+'-'+name,'serviceAccount':name,'audiences':['vault-vso'],'tokenExpirationSeconds':600}},'secrets.hashicorp.com/v1beta1')]
def vss(name,ns,role,mount,path,templates,typ='Opaque',restart=False):
    spec={'vaultAuthRef':role,'mount':mount,'path':path,'type':'kv-v2','refreshAfter':'60s','hmacSecretData':True,'destination':{'name':name,'create':True,'type':typ,'transformation':{'excludeRaw':True,'excludes':['.*'],'templates':{key:{'text':text} for key,text in templates.items()}}}}
    if restart:spec['rolloutRestartTargets']=[{'kind':'Deployment','name':'wallettracker-api'}]
    return obj('VaultStaticSecret',name,ns,spec,'secrets.hashicorp.com/v1beta1')
def resources(env):
    ns='wallettracker-'+env;prod=env=='prod';root=ROOT
    state=json.loads((root/'delivery/environment-state.json').read_text())
    if state.get('kubernetes_backup_policy')=='vault-only' and any(state['backup_enabled'].values()):
        raise ValueError('Owner policy allows Kubernetes backups only for Vault')
    if state['production_api_enabled'] and not state['production_restore_verified']:raise ValueError('Production activation requires reviewed restore proof')
    # Namespaces are operator bootstrap resources, not dev-controlled cluster
    # resources. Per-environment AppProjects cannot target another namespace.
    result=[obj('ServiceAccount','wallettracker',ns,automountServiceAccountToken=False)]
    for role in ['identity','database','pull']:result+=auth(role,ns)
    result += [obj('Role','vso-token-request',ns,api='rbac.authorization.k8s.io/v1',rules=[{'apiGroups':[''],'resources':['serviceaccounts/token'],'resourceNames':['identity','database','pull'],'verbs':['create']}]),obj('RoleBinding','vso-token-request',ns,api='rbac.authorization.k8s.io/v1',roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'vso-token-request'},subjects=[{'kind':'ServiceAccount','name':CTRL,'namespace':'vault-secrets-operator'}])]
    dbmount,dbpath=('downops','apps/wallettracker/runtime') if prod else ('wallettracker','dev/database')
    imount,ipath=('downops','apps/wallettracker/') if prod else ('wallettracker','dev/')
    result += [vss('wallettracker-db',ns,'database',dbmount,dbpath,{'MARIADB_ROOT_PASSWORD':'{{ .Secrets.DATABASE_ROOT_PASSWORD }}'}),vss('wallettracker-signing',ns,'identity',imount,ipath+'signing',{'WALLET_TRACKER_SECRET':'{{ .Secrets.SIGN_SECRET_WORD }}'},restart=True),vss('wallettracker-rsa',ns,'identity',imount,ipath+'rsa',{'private_key.pem':'{{ .Secrets.PRIVATE_KEY_BASE64 | b64dec }}','public_key.pem':'{{ .Secrets.PUBLIC_KEY_BASE64 | b64dec }}'},restart=True)]
    pull='{{- $auth := printf "%s:%s" .Secrets.HARBOR_ROBOT_NAME .Secrets.HARBOR_ROBOT_SECRET | b64enc -}}{{- $entry := dict "username" .Secrets.HARBOR_ROBOT_NAME "password" .Secrets.HARBOR_ROBOT_SECRET "auth" $auth -}}{{- dict "auths" (dict "registry.int.downops.win" $entry) | toJson -}}'
    result += [vss('harbor-pull',ns,'pull','wallettracker','delivery/harbor-pull',{'.dockerconfigjson':pull},'kubernetes.io/dockerconfigjson')]
    result += [obj('ConfigMap','wallettracker-config',ns,data={'DATABASE_NAME':'wallet_tracker','WALLET_TRACKER_DB_HOST':'mariadb','WALLET_TRACKER_DB_USER':'root','ENABLE_REGISTER':'false' if prod else 'true','WALLET_TRACKER_REQUIRE_MANAGED_KEYS':'true','WALLET_TRACKER_PRIVATE_KEY_FILE':'/run/wallettracker-rsa/private_key.pem','WALLET_TRACKER_PUBLIC_KEY_FILE':'/run/wallettracker-rsa/public_key.pem','WALLET_TRACKER_STDOUT_LOG':'true','WALLET_TRACKER_REQUIRE_RESTORE_CHECKPOINT':'true' if prod else 'false'})]
    if not prod:
        result[-1]['data'].update(WALLET_TRACKER_TRUSTED_PROXIES='10.2.0.10/32', WALLET_TRACKER_DEV_NETWORKS='10.2.0.0/24,192.168.1.0/24', WALLET_TRACKER_V2_ONLY='true')
    envdb=[{'name':'MARIADB_ROOT_PASSWORD','valueFrom':{'secretKeyRef':{'name':'wallettracker-db','key':'MARIADB_ROOT_PASSWORD'}}},{'name':'POD_IP','valueFrom':{'fieldRef':{'fieldPath':'status.podIP'}}}]
    db={'name':'mariadb','image':'mariadb:11.4.12','args':['--innodb-buffer-pool-size=64M','--max-connections=30','--performance-schema=OFF','--skip-name-resolve'],'env':envdb,'ports':[{'containerPort':3306,'name':'mysql'}],'securityContext':{'runAsNonRoot':True,'runAsUser':999,'runAsGroup':999,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'resources':{'requests':{'cpu':'50m','memory':'128Mi'},'limits':{'cpu':'500m','memory':'384Mi' if prod else '256Mi'}},'volumeMounts':[{'name':'data','mountPath':'/var/lib/mysql'},{'name':'run','mountPath':'/run/mysqld'},{'name':'tmp','mountPath':'/tmp'}],'startupProbe':{'exec':{'command':['sh','-ec','mariadb-admin ping --silent']},'periodSeconds':5,'failureThreshold':60},'livenessProbe':{'exec':{'command':['sh','-ec','mariadb-admin ping --silent']},'periodSeconds':15},'readinessProbe':{'exec':{'command':['sh','-ec','MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb --protocol=tcp -h "$POD_IP" -u root --batch -e "SELECT 1" >/dev/null']},'periodSeconds':10}}
    result += [obj('Service','mariadb',ns,{'ports':[{'port':3306,'targetPort':3306}],'selector':{'app':'wallettracker-db'}}),obj('StatefulSet','mariadb',ns,{'serviceName':'mariadb','replicas':1,'persistentVolumeClaimRetentionPolicy':{'whenDeleted':'Retain','whenScaled':'Retain'},'selector':{'matchLabels':{'app':'wallettracker-db'}},'template':{'metadata':{'labels':{'app':'wallettracker-db'}},'spec':{'serviceAccountName':'wallettracker','automountServiceAccountToken':False,'terminationGracePeriodSeconds':120,'securityContext':{'fsGroup':999,'fsGroupChangePolicy':'OnRootMismatch'},'containers':[db],'volumes':[{'name':'run','emptyDir':{}},{'name':'tmp','emptyDir':{}}]}},'volumeClaimTemplates':[{'metadata':{'name':'data'},'spec':{'accessModes':['ReadWriteOnce'],'storageClassName':'local-path','resources':{'requests':{'storage':'2Gi'}}}}]},'apps/v1')]
    api={'name':'api','image':IMAGE+':prepared-not-deployed','ports':[{'containerPort':5000,'name':'http'}],'envFrom':[{'configMapRef':{'name':'wallettracker-config'}},{'secretRef':{'name':'wallettracker-signing'}}],'env':[{'name':'DATABASE_ROOT_PASSWORD','valueFrom':{'secretKeyRef':{'name':'wallettracker-db','key':'MARIADB_ROOT_PASSWORD'}}}],'resources':{'requests':{'cpu':'50m','memory':'96Mi'},'limits':{'cpu':'500m','memory':'256Mi' if prod else '192Mi'}},'securityContext':{'runAsNonRoot':True,'runAsUser':10001,'runAsGroup':10001,'readOnlyRootFilesystem':True,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'volumeMounts':[{'name':'rsa','mountPath':'/run/wallettracker-rsa','readOnly':True},{'name':'tmp','mountPath':'/tmp'}],'startupProbe':{'httpGet':{'path':'/api/v1/health','port':5000},'failureThreshold':30,'periodSeconds':5},'livenessProbe':{'httpGet':{'path':'/api/v1/health','port':5000},'periodSeconds':15},'readinessProbe':{'httpGet':{'path':'/api/v1/ready','port':5000},'periodSeconds':5}}
    result += [obj('Deployment','wallettracker-api',ns,{'replicas':1 if not prod or state['production_api_enabled'] else 0,'revisionHistoryLimit':3,'strategy':{'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':0,'maxSurge':1}},'selector':{'matchLabels':{'app':'wallettracker-api'}},'template':{'metadata':{'labels':{'app':'wallettracker-api','wallettracker.io/database-client':'true'}},'spec':{'serviceAccountName':'wallettracker','automountServiceAccountToken':False,'imagePullSecrets':[{'name':'harbor-pull'}],'securityContext':{'fsGroup':10001},'terminationGracePeriodSeconds':45,'containers':[api],'volumes':[{'name':'rsa','secret':{'secretName':'wallettracker-rsa','defaultMode':288}},{'name':'tmp','emptyDir':{'medium':'Memory','sizeLimit':'32Mi'}}]}}},'apps/v1'),obj('Service','wallettracker-api',ns,{'type':'NodePort','externalTrafficPolicy':'Local','selector':{'app':'wallettracker-api'},'ports':[{'port':5000,'targetPort':5000,'nodePort':31411 if prod else 31410}]})]
    import copy
    jobapi=copy.deepcopy(api);jobapi['name']='migrate';jobapi.pop('startupProbe');jobapi.pop('livenessProbe');jobapi.pop('readinessProbe');jobapi['command']=['/app/.venv/bin/python','/migration/require_restore.py']
    jobapi['volumeMounts'].append({'name':'migration','mountPath':'/migration','readOnly':True})
    result += [obj('ConfigMap','wallettracker-migration',ns,data={'require_restore.py':(root/'delivery/require_restore.py').read_text()})]
    migrate=obj('Job','wallettracker-migrate',ns,{'backoffLimit':0,'activeDeadlineSeconds':600,'template':{'metadata':{'labels':{'wallettracker.io/database-client':'true'}},'spec':{'restartPolicy':'Never','serviceAccountName':'wallettracker','automountServiceAccountToken':False,'imagePullSecrets':[{'name':'harbor-pull'}],'securityContext':{'fsGroup':10001},'containers':[jobapi],'volumes':[{'name':'rsa','secret':{'secretName':'wallettracker-rsa','defaultMode':288}},{'name':'tmp','emptyDir':{}},{'name':'migration','configMap':{'name':'wallettracker-migration'}}]}}},'batch/v1')
    migrate['metadata']['annotations']={'argocd.argoproj.io/hook':'Sync','argocd.argoproj.io/hook-delete-policy':'BeforeHookCreation,HookSucceeded','argocd.argoproj.io/sync-wave':'0'};result.append(migrate)
    result.append(obj('PersistentVolumeClaim','wallettracker-backups',ns,{'accessModes':['ReadWriteOnce'],'storageClassName':'local-path','resources':{'requests':{'storage':'2Gi'}}}))
    backup={'name':'backup','image':'mariadb:11.4.12','command':['sh','-ec','umask 077; name="/backups/wallettracker-$(date -u +%Y%m%dT%H%M%SZ).sql.gz"; MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump -h mariadb -u root --all-databases --routines --events --triggers --single-transaction --hex-blob | gzip > "$name.tmp"; gzip -t "$name.tmp"; mv "$name.tmp" "$name"; echo "Database backup completed; payload withheld"'],'env':envdb[:1],'securityContext':{'runAsNonRoot':True,'runAsUser':999,'runAsGroup':999,'allowPrivilegeEscalation':False,'capabilities':{'drop':['ALL']}},'resources':{'requests':{'cpu':'25m','memory':'64Mi'},'limits':{'cpu':'250m','memory':'128Mi'}},'volumeMounts':[{'name':'backups','mountPath':'/backups'}]}
    # bash pipefail prevents a failed dump being mistaken for a valid empty gzip.
    backup['command'][:2]=['bash','-euo','pipefail','-c']
    backup['command'][-1]='ready=false; for attempt in {1..30}; do if MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb --protocol=tcp --connect-timeout=5 -h mariadb -u root -e "SELECT 1" >/dev/null 2>&1; then ready=true; break; fi; sleep 2; done; "$ready" || { echo "Database connectivity did not converge; backup refused"; exit 1; }; '+backup['command'][-1]
    result.append(obj('CronJob','wallettracker-backup',ns,{'schedule':'20 3 * * *','suspend':not state['backup_enabled'][env],'concurrencyPolicy':'Forbid','successfulJobsHistoryLimit':1,'failedJobsHistoryLimit':1,'jobTemplate':{'spec':{'backoffLimit':0,'activeDeadlineSeconds':600,'template':{'metadata':{'labels':{'wallettracker.io/database-client':'true'}},'spec':{'restartPolicy':'Never','serviceAccountName':'wallettracker','automountServiceAccountToken':False,'securityContext':{'fsGroup':999},'containers':[backup],'volumes':[{'name':'backups','persistentVolumeClaim':{'claimName':'wallettracker-backups'}}]}}}}},'batch/v1'))
    # A disabled backup must not create an unconsumed WaitForFirstConsumer PVC
    # in an early sync wave, or database/API creation can never start. Production
    # backup resources are retained/enabled only after their restore/export proof.
    if not state['backup_enabled'][env]:
        result=[r for r in result if r['metadata']['name'] not in ['wallettracker-backups','wallettracker-backup']]
    result += [obj('NetworkPolicy','default-deny',ns,{'podSelector':{},'policyTypes':['Ingress','Egress']},'networking.k8s.io/v1'),obj('NetworkPolicy','dns',ns,{'podSelector':{},'policyTypes':['Egress'],'egress':[{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}}}],'ports':[{'protocol':'UDP','port':53},{'protocol':'TCP','port':53}]}]},'networking.k8s.io/v1'),obj('NetworkPolicy','database',ns,{'podSelector':{'matchLabels':{'app':'wallettracker-db'}},'policyTypes':['Ingress'],'ingress':[{'from':[{'podSelector':{'matchLabels':{'wallettracker.io/database-client':'true'}}}],'ports':[{'protocol':'TCP','port':3306}]}]},'networking.k8s.io/v1'),obj('NetworkPolicy','api-egress',ns,{'podSelector':{'matchLabels':{'wallettracker.io/database-client':'true'}},'policyTypes':['Egress'],'egress':[{'to':[{'podSelector':{'matchLabels':{'app':'wallettracker-db'}}}],'ports':[{'protocol':'TCP','port':3306}]}]},'networking.k8s.io/v1'),obj('NetworkPolicy','api-ingress',ns,{'podSelector':{'matchLabels':{'app':'wallettracker-api'}},'policyTypes':['Ingress'],'ingress':[{'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}}},{'ipBlock':{'cidr':'10.2.0.10/32'}},{'ipBlock':{'cidr':'10.2.0.201/32'}}],'ports':[{'protocol':'TCP','port':5000}]}]},'networking.k8s.io/v1')]
    for r in result:
        if r['kind']=='Namespace' or r is migrate:continue
        wave='10' if r['kind']=='Deployment' else '-5' if r['kind']=='StatefulSet' else '-20'
        r['metadata'].setdefault('annotations',{})['argocd.argoproj.io/sync-wave']=wave
    for r in result:
        if r['kind'] in ['Deployment','StatefulSet','Job']:pod=r['spec']['template']['spec']
        elif r['kind']=='CronJob':pod=r['spec']['jobTemplate']['spec']['template']['spec']
        else:continue
        pod.setdefault('securityContext',{})['seccompProfile']={'type':'RuntimeDefault'}
    return result
def render(check=False):
    changed=[]
    for env in ['dev','prod']:
        folder=ROOT/'k8s'/env;folder.mkdir(parents=True,exist_ok=True)
        data=json.dumps({'apiVersion':'v1','kind':'List','items':resources(env)},indent=2)+'\n';p=folder/'resources.json'
        if check:
            if not p.exists() or p.read_text()!=data:changed.append(str(p.relative_to(ROOT)))
        else:p.write_text(data)
        k=folder/'kustomization.yaml'
        if not k.exists() and not check:k.write_text(json.dumps({'apiVersion':'kustomize.config.k8s.io/v1beta1','kind':'Kustomization','resources':['resources.json'],'images':[{'name':IMAGE,'newTag':'prepared-not-deployed'}]},indent=2)+'\n')
        ns='wallettracker-'+env;spec={'project':ns,'source':{'repoURL':'ssh://git@10.2.0.11:2222/downops/wallet-tracker-backend.git','targetRevision':'dev' if env=='dev' else 'main','path':'k8s/'+env},'destination':{'server':'https://kubernetes.default.svc','namespace':ns},'syncPolicy':{'syncOptions':['FailOnSharedResource=true']}}
        if env=='dev':spec['syncPolicy']['automated']={'prune':True,'selfHeal':True}
        app=obj('Application','wallettracker-'+env,'argocd',spec,'argoproj.io/v1alpha1');p=ROOT/'argocd'/(env+'.yaml');data=json.dumps(app,indent=2)+'\n'
        if check:
            if not p.exists() or p.read_text()!=data:changed.append(str(p.relative_to(ROOT)))
        else:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
    ns='argocd';role='wallettracker-repository'
    repoauth=[obj('ServiceAccount',role,ns,automountServiceAccountToken=False),obj('VaultAuth',role,ns,{'vaultConnectionRef':'vault-secrets-operator/default','method':'jwt','mount':'jwt','jwt':{'role':role,'serviceAccount':role,'audiences':['vault-vso'],'tokenExpirationSeconds':600}},'secrets.hashicorp.com/v1beta1')]
    repoauth += [obj('Role','wallettracker-repo-token-request',ns,api='rbac.authorization.k8s.io/v1',rules=[{'apiGroups':[''],'resources':['serviceaccounts/token'],'resourceNames':[role],'verbs':['create']}]),obj('RoleBinding','wallettracker-repo-token-request',ns,api='rbac.authorization.k8s.io/v1',roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'wallettracker-repo-token-request'},subjects=[{'kind':'ServiceAccount','name':CTRL,'namespace':'vault-secrets-operator'}])]
    secret=vss('wallettracker-repository',ns,role,'wallettracker','delivery/gitops-read',{'type':'git','url':'ssh://git@10.2.0.11:2222/downops/wallet-tracker-backend.git','sshPrivateKey':'{{ .Secrets.SSH_PRIVATE_KEY | trim | printf "%s\\n" }}','insecureIgnoreHostKey':'false'})
    secret['spec']['destination'].update(labels={'argocd.argoproj.io/secret-type':'repository'},annotations={'argocd.argoproj.io/secret-type':'repository'});repoauth.append(secret)
    credentialapp=obj('Application','wallettracker-credentials',ns,{'project':'wallettracker-credentials','source':{'repoURL':'ssh://git@10.2.0.11:2222/downops/wallet-tracker-backend.git','targetRevision':'main','path':'k8s/credentials'},'destination':{'server':'https://kubernetes.default.svc','namespace':'argocd'},'syncPolicy':{'automated':{'prune':False,'selfHeal':True}}},'argoproj.io/v1alpha1')
    for path,value in [('k8s/credentials/resources.json',{'apiVersion':'v1','kind':'List','items':repoauth}),('argocd/credentials.yaml',credentialapp)]:
        p=ROOT/path;data=json.dumps(value,indent=2)+'\n'
        if check:
            if not p.exists() or p.read_text()!=data:changed.append(path)
        else:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
    k=ROOT/'k8s/credentials/kustomization.yaml'
    if not k.exists() and not check:k.write_text(json.dumps({'apiVersion':'kustomize.config.k8s.io/v1beta1','kind':'Kustomization','resources':['resources.json']},indent=2)+'\n')
    projects=[]
    for env in ['dev','prod','credentials']:
        name='wallettracker-'+env;dest='argocd' if env=='credentials' else name
        project=obj('AppProject',name,'argocd',{'sourceRepos':['ssh://git@10.2.0.11:2222/downops/wallet-tracker-backend.git'],'destinations':[{'server':'https://kubernetes.default.svc','namespace':dest}],'clusterResourceWhitelist':[],'clusterResourceBlacklist':[{'group':'*','kind':'*'}],'namespaceResourceWhitelist':[{'group':'','kind':k} for k in ['Service','ConfigMap','ServiceAccount','PersistentVolumeClaim']]+[{'group':'apps','kind':k} for k in ['Deployment','StatefulSet']]+[{'group':'batch','kind':k} for k in ['Job','CronJob']]+[{'group':'networking.k8s.io','kind':'NetworkPolicy'},{'group':'rbac.authorization.k8s.io','kind':'Role'},{'group':'rbac.authorization.k8s.io','kind':'RoleBinding'},{'group':'secrets.hashicorp.com','kind':'VaultAuth'},{'group':'secrets.hashicorp.com','kind':'VaultStaticSecret'}],'roles':[{'name':'ci-status','policies':['p, proj:'+name+':ci-status, applications, get, '+name+'/'+name+', allow']} ]},'argoproj.io/v1alpha1')
        projects.append(project)
    namespaces=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'wallettracker-'+env,'labels':{'pod-security.kubernetes.io/enforce':'restricted','pod-security.kubernetes.io/enforce-version':'latest'},'annotations':{'argocd.argoproj.io/sync-options':'Prune=false,Delete=false'}}} for env in ['dev','prod']]
    for name,value in [('projects.json',projects),('namespaces.json',namespaces)]:
        p=ROOT/'bootstrap'/name;data=json.dumps({'apiVersion':'v1','kind':'List','items':value},indent=2)+'\n'
        if check:
            if not p.exists() or p.read_text()!=data:changed.append(str(p.relative_to(ROOT)))
        else:p.parent.mkdir(parents=True,exist_ok=True);p.write_text(data)
    if changed:raise SystemExit('Generated declarations drift: '+', '.join(changed))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');render(p.parse_args().check)
