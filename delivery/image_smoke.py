"""Ephemeral CI runtime probe only; never reads production credentials or data."""
import json,os,subprocess,time,urllib.request
if os.environ.get('CI')!='true':raise SystemExit('CI-only image probe')
if os.environ.get('DOCKER_HOST')!='tcp://docker:2375':raise SystemExit('Refusing non-disposable CI Docker endpoint')
def run(args):
    p=subprocess.run(['docker',*args],capture_output=True)
    if p.returncode:
        text=(p.stdout+p.stderr).decode(errors='replace');hints=[s for s in ['OperationalError','ImportError','ModuleNotFoundError','Connection refused','Access denied','Permission denied','libmariadb','libstdc++'] if s in text]
        paths=[s for s in ['/app/private_key.pem','/app/public_key.pem','/app/.venv/bin/python','/app/logs'] if s in text]
        print(json.dumps({'synthetic_operation_failed':args[0],'fixed_error_hints':hints,'known_runtime_error_paths':paths}))
        raise RuntimeError('Synthetic container operation failed; diagnostics withheld')
    return p.stdout
try:
    failure=subprocess.run(['docker','run','--name','wallettracker-ci-fail-closed','wallettracker-ci'],capture_output=True,timeout=60)
    if failure.returncode==0:raise RuntimeError('Image accepted missing managed identity')
    run(['network','create','wallettracker-ci'])
    run(['run','-d','--name','wallettracker-ci-db','--network','wallettracker-ci','--network-alias','db','-e','MARIADB_ROOT_PASSWORD=ci-only-not-production','mariadb:11.4.12'])
    for _ in range(60):
        p=subprocess.run(['docker','exec','-e','MYSQL_PWD=ci-only-not-production','wallettracker-ci-db','mariadb','--protocol=tcp','-h','127.0.0.1','-u','root','--batch','-e','SELECT 1'],capture_output=True)
        if p.returncode==0:break
        time.sleep(2)
    else:raise RuntimeError('Synthetic database startup failed')
    env=['DATABASE_ROOT_PASSWORD=ci-only-not-production','DATABASE_NAME=wallettracker_ci','WALLET_TRACKER_DB_HOST=db','WALLET_TRACKER_DB_USER=root','WALLET_TRACKER_SECRET=ci-only-signing-value','WALLET_TRACKER_STDOUT_LOG=true','WALLET_TRACKER_REQUIRE_MANAGED_KEYS=false']
    flags=[x for value in env for x in ['-e',value]]
    run(['run','--rm','--network','wallettracker-ci',*flags,'--entrypoint','/app/.venv/bin/python','wallettracker-ci','migrate_all.py'])
    run(['run','-d','--name','wallettracker-ci-api','--network','wallettracker-ci',*flags,'wallettracker-ci'])
    code="import urllib.request,json; r=urllib.request.urlopen('http://wallettracker-ci-api:5000/api/v1/ready'); assert json.load(r)['success']"
    for _ in range(30):
        p=subprocess.run(['docker','run','--rm','--network','wallettracker-ci','--entrypoint','/app/.venv/bin/python','wallettracker-ci','-c',code],capture_output=True)
        if p.returncode==0:break
        time.sleep(2)
    else:raise RuntimeError('Synthetic API/database readiness failed')
    print(json.dumps({'runtime_image_and_real_mariadb_ready':True,'production_secrets_used':False}))
finally:
    for name in ['wallettracker-ci-api','wallettracker-ci-db','wallettracker-ci-fail-closed']:subprocess.run(['docker','rm','-f','-v',name],capture_output=True)
    subprocess.run(['docker','network','rm','wallettracker-ci'],capture_output=True)
