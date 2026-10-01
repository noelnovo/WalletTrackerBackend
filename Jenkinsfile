pipeline {
    agent any
    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    parameters {
        string(name: 'GIT_BRANCH', defaultValue: 'main', description: 'Branch to build')
        string(name: 'IMAGE_VERSION', defaultValue: 'latest', description: 'Docker image version tag')
    }
    environment {
        VAULT_ADDR = credentials('vault-addr')
    }
    stages {
        stage('Checkout') {
            steps {
                git branch: "${params.GIT_BRANCH}", url: 'https://github.com/noelnovo/WalletTrackerBackend.git'
            }
        }
        stage('Vault dependent Stages') {
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
                        // Use shell environment variables instead of Groovy string interpolation so the
                        // registry hostname and image value are not exposed in the Jenkins command log.
                        // REGISTRY must be a bare hostname (registry.downops.win), no https://, no trailing path.
                        def registryHost = env.REGISTRY.replaceFirst(/^https?:\/\//, '').replaceAll(/\/.*/, '')
                        def imageTag = "${params.IMAGE_VERSION}"

                        withEnv([
                            "REGISTRY_HOST=${registryHost}",
                            "IMAGE_TAG=${imageTag}",
                            "IMAGE_NAME=${registryHost}/wallettracker/backend:${imageTag}"
                        ]) {
                            sh '''
                                set -euo pipefail
                                docker build -t "$IMAGE_NAME" ./app
                                echo "$DOCKER_PASSWORD" | docker login "$REGISTRY_HOST" -u "$DOCKER_USERNAME" --password-stdin
                                docker push "$IMAGE_NAME"
                                docker rmi "$IMAGE_NAME"
                                docker logout "$REGISTRY_HOST"
                            '''
                        }

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
