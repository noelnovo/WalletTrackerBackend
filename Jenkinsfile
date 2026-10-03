@Library('wallet-failover') _

pipeline {
    agent any
    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    parameters {
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Branch to build')
        string(name: 'IMAGE_VERSION', defaultValue: 'latest', description: 'Docker image version tag')
        string(name: 'PIPELINE_ORIGIN', defaultValue: 'github', description: 'Trigger origin: github|gitlab')
    }
    environment {
        VAULT_ADDR = credentials('vault-addr')
    }
    stages {
        // GitHub-primary failover gate (shared library):
        //  - GitHub available   -> run only the github-triggered build (gitlab trigger ignored)
        //  - GitHub unavailable -> run the gitlab-triggered build
        stage('Failover gate') {
            steps {
                script {
                    def origin = env.origin ?: params.PIPELINE_ORIGIN ?: 'github'
                    runPipelineWithFailover(origin: origin)
                }
            }
        }
        stage('Checkout') {
            when { expression { env.FAILOVER_RUN == 'true' } }
            steps {
                git branch: "${params.GIT_BRANCH}", url: 'https://github.com/noelnovo/WalletTrackerBackend.git'
            }
        }
        stage('Vault dependent Stages') {
            when { expression { env.FAILOVER_RUN == 'true' } }
            steps {
                script {
                    // vault token fetching
                    withCredentials([[$class: 'VaultTokenCredentialBinding', credentialsId: 'wallettracker-vault-token', vaultAddr: env.VAULT_ADDR]]) {
                    withVault(
                        configuration: [
                            vaultUrl: env.VAULT_ADDR,
                            vaultCredentialId: 'wallettracker-vault-token',
                            engineVersion: 2
                        ],
                        // vault secrets fetching
                        vaultSecrets: [
                            [
                                path: "downops/wallettracker.backend",
                                engineVersion: 2,
                                secretValues: [
                                    [envVar: 'REGISTRY',        vaultKey: 'HARBOR_HOSTNAME'],
                                    [envVar: 'DOCKER_USERNAME', vaultKey: 'HARBOR_ROBOT_NAME'],
                                    [envVar: 'DOCKER_PASSWORD', vaultKey: 'HARBOR_ROBOT_SECRET']
                                ]
                            ]
                        ]
                    ) {
                        // Push wallet tracker image to registry, then remove local copy to free disk space.
                        // Keep all sensitive values in shell environment only; do not read or interpolate
                        // Vault-provided secrets in Groovy before the shell executes.
                        sh '''
                            set -euo pipefail

                            REGISTRY_HOST="${REGISTRY#https://}"
                            REGISTRY_HOST="${REGISTRY_HOST%%/*}"
                            IMAGE_NAME="${REGISTRY_HOST}/wallettracker/backend:${IMAGE_VERSION}"

                            docker build -t "$IMAGE_NAME" ./app
                            echo "$DOCKER_PASSWORD" | docker login "$REGISTRY_HOST" -u "$DOCKER_USERNAME" --password-stdin
                            docker push "$IMAGE_NAME"
                            docker rmi "$IMAGE_NAME"
                            docker logout "$REGISTRY_HOST"
                        '''

                        // run Terraform deployment to Proxmox
                        dir('terraform') {
                            sh 'terraform init'
                            retry(3) {
                                sh 'terraform plan'
                            }
                            retry(3) {
                                sh 'terraform apply -auto-approve'
                            }
                        }
                    }
                    }
                }
            }
        }
    }
}
