pipeline {
    agent any

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

        stage('Terraform Init') {
            steps {
                dir("${TF_DIR}") { sh 'terraform init -input=false' }
            }
        }

        stage('Terraform Validate') {
            steps {
                dir("${TF_DIR}") { sh 'terraform validate' }
            }
        }

        stage('Terraform Plan') {
            steps {
                dir("${TF_DIR}") { sh 'terraform plan -out=tfplan' }
            }
        }

        stage('Approval') {
            steps {
                input message: 'Approve Terraform deployment?', ok: 'Deploy'
            }
        }

        stage('Terraform Apply') {
            steps {
                script {
                    int rc = sh(script: "cd ${TF_DIR} && terraform apply -auto-approve tfplan > ../terraform-apply.log 2>&1", returnStatus: true)
                    if (rc != 0) {
                        currentBuild.description = 'Terraform apply failed — AI remediation started'
                        error('Terraform Apply failed; entering AI remediation stage')
                    }
                }
            }
        }

        stage('AI Remediation') {
            when {
                expression { currentBuild.currentResult == 'FAILURE' }
            }
            steps {
                script {
                    // The MVP agent is intentionally executed inside the Jenkins
                    // workspace. It can edit only Terraform/YAML files there.
                    sh "python3 agent/remediate.py --workspace ${TF_DIR} --log terraform-apply.log --max-attempts ${MAX_AI_REMEDIATION_ATTEMPTS} > ai-remediation.json"
                    archiveArtifacts artifacts: 'ai-remediation.json,terraform-apply.log', fingerprint: true
                }
            }
        }

        stage('Re-Apply After AI Fix') {
            when {
                expression { fileExists('ai-remediation.json') }
            }
            steps {
                script {
                    int rc = sh(script: "cd ${TF_DIR} && terraform apply -auto-approve ai-remediation.tfplan", returnStatus: true)
                    if (rc != 0) {
                        error('AI remediation validation/plan succeeded, but re-apply failed')
                    }
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
