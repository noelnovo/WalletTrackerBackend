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
                                path: "downops/common",
                                engineVersion: 2,
                                secretValues: [
                                    [envVar: 'REGISTRY',        vaultKey: 'REGISTRY_IP'],
                                    [envVar: 'DOCKER_USERNAME', vaultKey: 'REGISTRY_USER'],
                                    [envVar: 'DOCKER_PASSWORD', vaultKey: 'REGISTRY_PASSWORD']
                                ]
                            ]
                        ]
                    ) {
                        // Push wallet tracker image to registry, then remove local copy to free disk space.
                        // sh uses 'set -e': if push fails the build stops and rmi is skipped.
                        def image = "${env.REGISTRY}/wallet-tracker:${params.IMAGE_VERSION}"
                        sh """
                            echo "\$DOCKER_PASSWORD" | docker login \$REGISTRY -u "\$DOCKER_USERNAME" --password-stdin
                            docker push ${image}
                            docker rmi ${image}
                            docker logout \$REGISTRY
                        """

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
