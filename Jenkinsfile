pipeline {
    agent any
    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timeout(time: 60, unit: 'MINUTES')
    }
    parameters {
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Production maintenance branch (main only)')
        string(name: 'SOURCE_REVISION', defaultValue: '', description: 'Exact tested commit SHA; empty resolves current main for plan-only runs')
        booleanParam(name: 'APPLY', defaultValue: false, description: 'Request production apply; also requires explicit approval of the saved plan')
    }
    environment {
        VAULT_ADDR = 'https://vault.int.downops.win'
    }
    stages {
        stage('Checkout') {
            steps {
                script {
                    if (params.GIT_BRANCH != 'main') {
                        error('This existing production job may deploy main only')
                    }
                    if (params.SOURCE_REVISION && !(params.SOURCE_REVISION ==~ /[0-9a-f]{40}/)) {
                        error('SOURCE_REVISION must be a full commit SHA')
                    }
                }
                // Preserve the sole Jenkins Terraform workspace and its local state.
                git branch: 'main', url: 'https://github.com/noelnovo/WalletTrackerBackend.git'
                script {
                    env.SOURCE_REVISION = params.SOURCE_REVISION ?: env.CORRELATION_ID ?: sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    if (!(env.SOURCE_REVISION ==~ /[0-9a-f]{40}/)) {
                        error('Resolved source revision must be a full commit SHA')
                    }
                }
                sh '''#!/bin/sh
                    set -eu
                    git cat-file -e "$SOURCE_REVISION^{commit}"
                    git merge-base --is-ancestor "$SOURCE_REVISION" origin/main
                    git checkout --detach "$SOURCE_REVISION"
                    python3 terraform/vault-agent/test_delivery.py
                    python3 -m unittest discover -s terraform -p 'test_*.py'
                '''
            }
        }
        stage('Plan and approved deployment') {
            steps {
                script {
                    withCredentials([[$class: 'VaultTokenCredentialBinding', credentialsId: 'wallettracker-vault-token', vaultAddr: env.VAULT_ADDR]]) {
                        dir('terraform') {
                            // Plan/state/logs are credential-bearing. Never archive or echo them.
                            sh '''#!/bin/sh
                                set -eu
                                umask 077
                                test -s terraform.tfstate || { echo 'Existing production state required; refusing empty workspace'; exit 1; }
                                chmod 600 terraform.tfstate
                                export TF_VAR_source_revision="$SOURCE_REVISION"
                                export TF_IN_AUTOMATION=1
                                if ! terraform init -input=false -no-color > init.private.log 2>&1; then
                                    echo 'Terraform init failed; inspect protected workspace diagnostics'; exit 1
                                fi
                                if ! terraform plan -input=false -no-color -out=release.tfplan > plan.private.log 2>&1; then
                                    echo 'Terraform plan failed; inspect protected workspace diagnostics'; exit 1
                                fi
                                terraform show -json release.tfplan > release.private.json
                                python3 check_plan.py < release.private.json
                            '''
                            if (params.APPLY) {
                                input message: "Apply the reviewed WalletTracker plan for ${env.SOURCE_REVISION}? This backs up MariaDB and briefly stops API LXC 101 for migrations; database LXC 102 is not replaced.", ok: 'Approve production deployment'
                                withVault(configuration: [vaultUrl: env.VAULT_ADDR, vaultCredentialId: 'wallettracker-vault-token', engineVersion: 2], vaultSecrets: [
                                    [path: 'downops/apps/wallettracker/provisioning', engineVersion: 2, secretValues: [
                                        [envVar: 'DOCKER_USERNAME', vaultKey: 'HARBOR_ROBOT_NAME'],
                                        [envVar: 'DOCKER_PASSWORD', vaultKey: 'HARBOR_ROBOT_SECRET']]],
                                    [path: 'downops/services/harbor/urls', engineVersion: 2, secretValues: [[envVar: 'REGISTRY', vaultKey: 'HARBOR_INTERNAL_URL']]]
                                ]) {
                                    sh '''#!/bin/sh
                                        set -eu
                                        umask 077
                                        REGISTRY_HOST="${REGISTRY#https://}"
                                        REGISTRY_HOST="${REGISTRY_HOST%%/*}"
                                        IMAGE_NAME="$REGISTRY_HOST/downops/wallettracker-backend:git-$SOURCE_REVISION"
                                        DOCKER_CONFIG="$(mktemp -d)"
                                        export DOCKER_CONFIG
                                        trap 'docker logout "$REGISTRY_HOST" >/dev/null 2>&1 || true; rm -f "$DOCKER_CONFIG/config.json"; rmdir "$DOCKER_CONFIG" 2>/dev/null || true' EXIT
                                        docker build -t "$IMAGE_NAME" ../app
                                        docker run --rm -e ENABLE_REGISTER=true -v "$PWD/../tests:/tests:ro" --entrypoint /app/.venv/bin/pytest "$IMAGE_NAME" /tests -o pythonpath=/app -q
                                        printf '%s' "$DOCKER_PASSWORD" | docker login "$REGISTRY_HOST" -u "$DOCKER_USERNAME" --password-stdin
                                        docker push "$IMAGE_NAME"
                                        docker rmi "$IMAGE_NAME"
                                        export TF_VAR_source_revision="$SOURCE_REVISION"
                                        if ! terraform apply -input=false -no-color release.tfplan > apply.private.log 2>&1; then
                                            echo 'Deployment failed; inspect protected workspace diagnostics; no automatic apply retry'; exit 1
                                        fi
                                    '''
                                }
                                sh '''#!/bin/sh
                                    set -eu
                                    python3 - <<'PY'
import json, urllib.request
with urllib.request.urlopen('https://api.downops.win/api/v1/ready', timeout=30) as response:
    assert response.status == 200 and json.load(response)['success'] is True
print('Public API and database readiness verified')
PY
                                '''
                            } else {
                                echo 'Plan-only run: production was not changed'
                            }
                        }
                    }
                }
            }
        }
    }
    post {
        always {
            sh '''#!/bin/sh
                set -eu
                for file in terraform/release.tfplan terraform/release.private.json; do
                    if [ -f "$file" ]; then rm "$file"; fi
                done
            '''
        }
    }
}
