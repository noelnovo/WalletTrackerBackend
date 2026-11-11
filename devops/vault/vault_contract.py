"""Desired scoped policies/roles. Pure data; never acquires administrative access."""
def read_policy(paths):
    return '\n'.join('path "'+p+'" { capabilities=["read"] }' for p in paths)+'\npath "auth/token/lookup-self" { capabilities=["read"] }\npath "auth/token/renew-self" { capabilities=["update"] }\npath "auth/token/revoke-self" { capabilities=["update"] }\n'
def contract(canonical_dev=True):
    if not canonical_dev:
        raise ValueError('Legacy mount contracts are retired; no replayable rollback plan')
    policies={};roles={}
    for env in ['dev','prod']:
        ns='wallettracker-'+env;prod=env=='prod'
        prefix='downops/data/apps/wallettracker/'+env+'/'
        pull_path='downops/data/apps/wallettracker/delivery/harbor-pull'
        paths={'identity':[prefix+'rsa',prefix+'signing'],'database':[prefix+'runtime'],'pull':[pull_path]}
        # Preserve verified production grants until explicit reader retirement.
        if prod:
            paths['identity'] += ['downops/data/apps/wallettracker/rsa','downops/data/apps/wallettracker/signing']
            paths['database'] += ['downops/data/apps/wallettracker/runtime']
        paths['pull'].append('downops/data/services/harbor/pull/instance-004')
        for sa,reads in paths.items():
            name=ns+'-'+sa;policies[name]=read_policy(reads)
            roles['jwt/'+name]={'role_type':'jwt','user_claim':'sub','bound_subject':'system:serviceaccount:'+ns+':'+sa,'bound_audiences':['vault-vso'],'token_policies':[name],'token_no_default_policy':True,'token_type':'service','token_ttl':900,'token_max_ttl':3600}
    name='wallettracker-repository';policies[name]=read_policy(['downops/data/apps/wallettracker/delivery/gitops-read'])
    roles['jwt/'+name]={'role_type':'jwt','user_claim':'sub','bound_subject':'system:serviceaccount:argocd:wallettracker-repository','bound_audiences':['vault-vso'],'token_policies':[name],'token_no_default_policy':True,'token_type':'service','token_ttl':900,'token_max_ttl':3600}
    for env in ['dev','prod','scan']:
        name='wallettracker-ci-'+env
        status_path='downops/data/apps/wallettracker/delivery/argocd-'+env
        paths=['downops/data/services/sonarqube/clients/instance-001','downops/data/services/dependency-track/clients/instance-001'] if env=='scan' else ['downops/data/apps/wallettracker/delivery/harbor-ci','downops/data/apps/wallettracker/delivery/github-mirror',status_path]
        if env!='scan':paths.append('downops/data/services/harbor/ci/instance-004')
        policies[name]=read_policy(paths)
        claims={'project_id':'1','namespace_path':'downops'}
        if env=='prod':claims.update(ref_type='tag',ref='v*',ref_protected='true')
        elif env=='dev':claims.update(ref_type='branch',ref='dev',ref_protected='true')
        else:claims.update(ref_type=['branch','tag'],ref=['dev','main','v*'],ref_protected='true')
        roles['gitlab-ci/'+name]={'role_type':'jwt','user_claim':'user_id','bound_audiences':['https://vault.int.downops.win'],'bound_claims_type':'glob','bound_claims':claims,'token_policies':[name],'token_no_default_policy':True,'token_type':'batch','token_ttl':900,'token_max_ttl':900}
    # Android owns its separate four-read scanner and owner-only signing roles
    # in project31/config/signing/gitlab-delivery-vault-plan.json. Do not recreate
    # the retired combined branch-scanner/production-keystore grant here.
    return {'policies':policies,'roles':roles,'create_auth_mount_if_absent':{'gitlab-ci':{'type':'jwt','config':{'oidc_discovery_url':'https://gitlab.downops.win','bound_issuer':'https://gitlab.downops.win'}}},'reuse_shared_kubernetes_auth_mount_without_changes':'jwt','new_kv_mount':None,'canonical_kv_mount':'downops','canonical_app_prefix':'apps/wallettracker','canonical_dev_plan':canonical_dev,'required_input_records':{'downops/apps/wallettracker/dev/runtime':['DATABASE_ROOT_PASSWORD'],'downops/apps/wallettracker/dev/rsa':['PRIVATE_KEY_BASE64','PUBLIC_KEY_BASE64'],'downops/apps/wallettracker/dev/signing':['SIGN_SECRET_WORD'],'downops/services/harbor/ci/instance-004':['HARBOR_ROBOT_NAME','HARBOR_ROBOT_SECRET'],'downops/services/harbor/pull/instance-004':['HARBOR_ROBOT_NAME','HARBOR_ROBOT_SECRET'],'downops/apps/wallettracker/delivery/github-mirror':['SSH_PRIVATE_KEY','KNOWN_HOSTS'],'downops/apps/wallettracker/delivery/argocd-dev':['TOKEN']} if canonical_dev else {'wallettracker/dev/database':['DATABASE_ROOT_PASSWORD'],'wallettracker/dev/rsa':['PRIVATE_KEY_BASE64','PUBLIC_KEY_BASE64'],'wallettracker/dev/signing':['SIGN_SECRET_WORD'],'wallettracker/delivery/argocd-dev':['TOKEN']},'legacy_shared_records_preserved':['wallettracker/delivery/harbor-ci','wallettracker/delivery/harbor-pull','wallettracker/delivery/gitops-read','wallettracker/delivery/github-mirror','wallettracker/delivery/argocd-prod']}
if __name__=='__main__':
    import json;print(json.dumps(contract(),indent=2))
