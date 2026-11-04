"""Desired scoped policies/roles. Pure data; never acquires administrative access."""
def read_policy(paths):
    return '\n'.join('path "'+p+'" { capabilities=["read"] }' for p in paths)+'\npath "auth/token/lookup-self" { capabilities=["read"] }\npath "auth/token/renew-self" { capabilities=["update"] }\npath "auth/token/revoke-self" { capabilities=["update"] }\n'
def contract():
    policies={};roles={}
    for env in ['dev','prod']:
        ns='wallettracker-'+env;prod=env=='prod'
        prefix='downops/data/apps/wallettracker/' if prod else 'wallettracker/data/dev/'
        paths={'identity':[prefix+'rsa',prefix+'signing'],'database':[prefix+('runtime' if prod else 'database')],'pull':['wallettracker/data/delivery/harbor-pull']}
        for sa,reads in paths.items():
            name=ns+'-'+sa;policies[name]=read_policy(reads)
            roles['jwt/'+name]={'role_type':'jwt','user_claim':'sub','bound_subject':'system:serviceaccount:'+ns+':'+sa,'bound_audiences':['vault-vso'],'token_policies':[name],'token_no_default_policy':True,'token_type':'service','token_ttl':900,'token_max_ttl':3600}
    name='wallettracker-repository';policies[name]=read_policy(['wallettracker/data/delivery/gitops-read'])
    roles['jwt/'+name]={'role_type':'jwt','user_claim':'sub','bound_subject':'system:serviceaccount:argocd:wallettracker-repository','bound_audiences':['vault-vso'],'token_policies':[name],'token_no_default_policy':True,'token_type':'service','token_ttl':900,'token_max_ttl':3600}
    for env in ['dev','prod','scan']:
        name='wallettracker-ci-'+env
        paths=['downops/data/services/sonarqube/clients/instance-001','downops/data/services/dependency-track/clients/instance-001'] if env=='scan' else ['wallettracker/data/delivery/harbor-ci','wallettracker/data/delivery/github-mirror','wallettracker/data/delivery/argocd-'+env]
        policies[name]=read_policy(paths)
        claims={'project_id':'1','namespace_path':'downops'}
        if env=='prod':claims.update(ref_type='tag',ref='v*',ref_protected='true')
        elif env=='dev':claims.update(ref_type='branch',ref='dev')
        roles['gitlab-ci/'+name]={'role_type':'jwt','user_claim':'user_id','bound_audiences':['https://vault.int.downops.win'],'bound_claims_type':'glob','bound_claims':claims,'token_policies':[name],'token_no_default_policy':True,'token_type':'batch','token_ttl':900,'token_max_ttl':900}
    return {'policies':policies,'roles':roles,'create_auth_mount_if_absent':{'gitlab-ci':{'type':'jwt','config':{'oidc_discovery_url':'https://gitlab.downops.win','bound_issuer':'https://gitlab.downops.win'}}},'reuse_shared_kubernetes_auth_mount_without_changes':'jwt','new_kv_mount':'wallettracker','required_input_records':{'delivery/harbor-ci':['HARBOR_ROBOT_NAME','HARBOR_ROBOT_SECRET'],'delivery/harbor-pull':['HARBOR_ROBOT_NAME','HARBOR_ROBOT_SECRET'],'delivery/gitops-read':['SSH_PRIVATE_KEY'],'delivery/github-mirror':['SSH_PRIVATE_KEY','KNOWN_HOSTS'],'delivery/argocd-dev':['TOKEN'],'delivery/argocd-prod':['TOKEN']}}
if __name__=='__main__':
    import json;print(json.dumps(contract(),indent=2))
