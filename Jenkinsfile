pipeline {
    agent { label 'Windows-Agent' }

    environment {
        TF_IN_AUTOMATION = 'true'
        TF_INPUT = 'false'
        TF_DIR = 'terraform'
        MAX_AI_REMEDIATION_ATTEMPTS = '1'
        // Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_MODEL in Jenkins
        // global/node environment configuration. Never commit API keys.
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Tool Check') {
            steps {
                bat 'terraform version'
                bat 'python --version'
                bat 'python -m pip --version'
            }
        }

        stage('AI Configuration Check') {
            steps {
                bat 'if not defined AZURE_OPENAI_ENDPOINT exit /b 1'
                bat 'if not defined AZURE_OPENAI_MODEL exit /b 1'
            }
        }

        stage('Install AI Dependencies') {
            steps {
                bat 'python -m pip install --disable-pip-version-check -r requirements.txt'
            }
        }

        stage('Terraform Init') {
            steps { dir("${TF_DIR}") { bat 'terraform init -input=false' } }
        }

        stage('Terraform Validate') {
            steps { dir("${TF_DIR}") { bat 'terraform validate' } }
        }

        stage('Terraform Plan') {
            steps { dir("${TF_DIR}") { bat 'terraform plan -out=tfplan' } }
        }

        stage('Approval') {
            steps { input message: 'Approve Terraform deployment?', ok: 'Deploy' }
        }

        stage('Terraform Apply') {
            steps {
                script {
                    int rc = bat(
                        script: 'cd terraform && terraform apply -auto-approve tfplan > ..\\terraform-apply.log 2>&1',
                        returnStatus: true
                    )
                    if (rc != 0) {
                        env.TERRAFORM_APPLY_FAILED = 'true'
                        currentBuild.description = 'Terraform apply failed - AI remediation started'
                        echo 'Terraform Apply failed. Continuing to AI remediation.'
                    } else {
                        env.TERRAFORM_APPLY_FAILED = 'false'
                    }
                }
            }
        }

        stage('AI Remediation') {
            when {
                expression { env.TERRAFORM_APPLY_FAILED == 'true' }
            }
            steps {
                script {
                    withCredentials([string(credentialsId: 'azure-openai-api-key', variable: 'AZURE_OPENAI_API_KEY')]) {
                        int rc = bat(
                            script: 'python agent\\ai_remediate.py --workspace terraform --log terraform-apply.log > ai-remediation.json',
                            returnStatus: true
                        )
                        archiveArtifacts artifacts: 'ai-remediation.json,terraform-apply.log', fingerprint: true
                        if (rc != 0) {
                            error('AI agent did not produce a validated safe remediation')
                        }
                    }
                }
            }
        }

        stage('Re-Apply After AI Fix') {
            when {
                expression { env.TERRAFORM_APPLY_FAILED == 'true' && fileExists('terraform/ai-remediation.tfplan') }
            }
            steps {
                script {
                    int rc = bat(
                        script: 'cd terraform && terraform apply -auto-approve ai-remediation.tfplan',
                        returnStatus: true
                    )
                    if (rc != 0) {
                        error('AI remediation validation/plan succeeded, but re-apply failed')
                    }
                    env.TERRAFORM_APPLY_FAILED = 'false'
                    currentBuild.description = 'Deployment recovered by AI remediation'
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'terraform-apply.log,ai-remediation.json', allowEmptyArchive: true, fingerprint: true
        }
    }
}
