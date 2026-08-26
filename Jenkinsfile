pipeline {
    agent { label 'Windows-Agent' }

    environment {
        TF_IN_AUTOMATION = 'true'
        TF_INPUT = 'false'
        TF_DIR = 'terraform'
        MAX_AI_REMEDIATION_ATTEMPTS = '1'
    }

    stages {
        stage('Checkout') {
            steps { checkout scm }
        }

        stage('Tool Check') {
            steps {
                bat 'terraform version'
                bat 'python --version'
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
                        echo 'Terraform Apply failed. Continuing to controlled AI remediation.'
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
                    int rc = bat(
                        script: 'python agent\\remediate.py --workspace terraform --log terraform-apply.log --max-attempts %MAX_AI_REMEDIATION_ATTEMPTS% > ai-remediation.json',
                        returnStatus: true
                    )
                    archiveArtifacts artifacts: 'ai-remediation.json,terraform-apply.log', fingerprint: true
                    if (rc != 0) {
                        error('AI agent could not produce a validated safe remediation')
                    }
                }
            }
        }

        stage('Re-Apply After AI Fix') {
            when {
                expression { env.TERRAFORM_APPLY_FAILED == 'true' && fileExists('ai-remediation.json') }
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
