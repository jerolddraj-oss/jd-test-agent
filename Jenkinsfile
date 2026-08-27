pipeline {
    agent { label 'Windows-Agent' }

    parameters {
        choice(
            name: 'ACTION',
            choices: ['DEPLOY', 'DESTROY'],
            description: 'DEPLOY creates/repairs the test environment. DESTROY removes the Terraform-managed test environment.'
        )
    }

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
                bat 'python -m pip --version'
                bat 'az version'
            }
        }

        stage('Azure Authentication Check') {
            steps {
                withCredentials([
                    string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                    string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                    string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                    string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID'),
                    string(credentialsId: 'azure-vm-admin-password', variable: 'TF_VAR_admin_password')
                ]) {
                    bat 'if not defined ARM_CLIENT_ID exit /b 1'
                    bat 'if not defined ARM_CLIENT_SECRET exit /b 1'
                    bat 'if not defined ARM_TENANT_ID exit /b 1'
                    bat 'if not defined ARM_SUBSCRIPTION_ID exit /b 1'
                    bat 'if not defined TF_VAR_admin_password exit /b 1'
                    echo 'Azure authentication and VM password credentials are configured.'
                }
            }
        }

        stage('Terraform Destroy') {
            when {
                expression { params.ACTION == 'DESTROY' }
            }
            steps {
                script {
                    input message: 'WARNING: Destroy the Agentic Terraform test environment and both Azure VMs?', ok: 'Destroy'

                    withCredentials([
                        string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID'),
                        string(credentialsId: 'azure-vm-admin-password', variable: 'TF_VAR_admin_password')
                    ]) {
                        dir("${TF_DIR}") {
                            bat 'terraform init -input=false'
                            bat 'terraform destroy -auto-approve -input=false'
                        }
                    }
                }
            }
        }

        stage('AI Configuration Check') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                bat 'if not defined AZURE_OPENAI_ENDPOINT exit /b 1'
                bat 'if not defined AZURE_OPENAI_MODEL exit /b 1'
            }
        }

        stage('Azure OpenAI Connectivity Test') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'azure-openai-api-key', variable: 'AZURE_OPENAI_API_KEY')
                ]) {
                    bat '''
                        python -c "import os; from openai import OpenAI; c=OpenAI(api_key=os.environ['AZURE_OPENAI_API_KEY'], base_url=os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/') + '/openai/v1/'); r=c.responses.create(model=os.environ['AZURE_OPENAI_MODEL'], input='Reply with exactly: AZURE_OPENAI_TEST_OK'); print(r.output_text)"
                    '''
                }
            }
        }

        stage('Install AI Dependencies') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                bat 'python -m pip install --disable-pip-version-check -r requirements.txt'
            }
        }

        stage('Terraform Init') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                    string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                    string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                    string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID')
                ]) {
                    dir("${TF_DIR}") {
                        bat 'terraform init -input=false'
                    }
                }
            }
        }

        stage('Terraform Validate') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                    string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                    string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                    string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID'),
                    string(credentialsId: 'azure-vm-admin-password', variable: 'TF_VAR_admin_password')
                ]) {
                    dir("${TF_DIR}") {
                        bat 'terraform validate'
                    }
                }
            }
        }

        stage('Terraform Plan') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                    string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                    string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                    string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID'),
                    string(credentialsId: 'azure-vm-admin-password', variable: 'TF_VAR_admin_password')
                ]) {
                    dir("${TF_DIR}") {
                        bat 'terraform plan -input=false -out=tfplan'
                    }
                }
            }
        }

        stage('Approval') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                input message: 'Approve Terraform deployment of the two test VMs?', ok: 'Deploy'
            }
        }

        stage('Terraform Apply') {
            when {
                expression { params.ACTION == 'DEPLOY' }
            }
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID'),
                        string(credentialsId: 'azure-vm-admin-password', variable: 'TF_VAR_admin_password')
                    ]) {
                        int rc = bat(
                            script: 'cd terraform && terraform apply -auto-approve tfplan > ..\\terraform-apply.log 2>&1',
                            returnStatus: true
                        )

                        if (rc != 0) {
                            env.TERRAFORM_APPLY_FAILED = 'true'
                            currentBuild.description = 'Terraform apply failed - AI remediation started'
                            echo 'Terraform Apply failed. Continuing to AI remediation.'
                            bat 'type terraform-apply.log'
                        } else {
                            env.TERRAFORM_APPLY_FAILED = 'false'
                        }
                    }
                }
            }
        }

        stage('AI Remediation') {
            when {
                expression { params.ACTION == 'DEPLOY' && env.TERRAFORM_APPLY_FAILED == 'true' }
            }
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'azure-openai-api-key', variable: 'AZURE_OPENAI_API_KEY')
                    ]) {
                        int rc = bat(
                            script: 'python agent\\ai_remediate.py --workspace terraform --log terraform-apply.log > ai-remediation.json 2> ai-remediation-error.log',
                            returnStatus: true
                        )

                        archiveArtifacts(
                            artifacts: 'ai-remediation.json,ai-remediation-error.log,terraform-apply.log,terraform/main.tf.ai-backup',
                            allowEmptyArchive: true,
                            fingerprint: true
                        )

                        if (rc != 0) {
                            bat 'type ai-remediation.json'
                            bat 'if exist ai-remediation-error.log type ai-remediation-error.log'
                            error('AI agent did not produce a validated safe remediation')
                        }
                    }
                }
            }
        }

        stage('Re-Apply After AI Fix') {
            when {
                expression {
                    params.ACTION == 'DEPLOY' && env.TERRAFORM_APPLY_FAILED == 'true' && fileExists('terraform/ai-remediation.tfplan')
                }
            }
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID'),
                        string(credentialsId: 'azure-vm-admin-password', variable: 'TF_VAR_admin_password')
                    ]) {
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

        stage('Terraform Outputs') {
            when {
                expression { params.ACTION == 'DEPLOY' && env.TERRAFORM_APPLY_FAILED != 'true' }
            }
            steps {
                withCredentials([
                    string(credentialsId: 'azure-client-id', variable: 'ARM_CLIENT_ID'),
                    string(credentialsId: 'azure-client-secret', variable: 'ARM_CLIENT_SECRET'),
                    string(credentialsId: 'azure-tenant-id', variable: 'ARM_TENANT_ID'),
                    string(credentialsId: 'azure-subscription-id', variable: 'ARM_SUBSCRIPTION_ID'),
                    string(credentialsId: 'azure-vm-admin-password', variable: 'TF_VAR_admin_password')
                ]) {
                    dir("${TF_DIR}") {
                        bat 'terraform output'
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts(
                artifacts: 'terraform-apply.log,ai-remediation.json,ai-remediation-error.log,terraform/terraform.tfstate',
                allowEmptyArchive: true,
                fingerprint: true
            )
        }
    }
}
