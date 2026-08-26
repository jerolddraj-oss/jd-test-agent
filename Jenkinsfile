pipeline {
    agent { label 'Windows-Agent' }

    environment {
        TF_IN_AUTOMATION = 'true'
        TF_INPUT = 'false'
        TF_DIR = 'terraform'
        MAX_AI_REMEDIATION_ATTEMPTS = '1'

        // MVP-2 uses a LOCAL-ONLY Terraform test configuration.
        // Do not copy the reset stage into production pipelines.
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
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

        /*
         * TEMPORARY MVP-2 TEST
         *
         * This stage verifies:
         *   Jenkins Credential
         *        ↓
         *   Azure OpenAI
         *        ↓
         *   Responses API
         *        ↓
         *   GPT deployment
         *
         * The API key is never printed.
         */
        stage('Azure OpenAI Connectivity Test') {
            steps {
                withCredentials([
                    string(
                        credentialsId: 'azure-openai-api-key',
                        variable: 'AZURE_OPENAI_API_KEY'
                    )
                ]) {
                    bat '''
                        python -c "import os; from openai import OpenAI; c=OpenAI(api_key=os.environ['AZURE_OPENAI_API_KEY'], base_url=os.environ['AZURE_OPENAI_ENDPOINT'].rstrip('/') + '/openai/v1/'); r=c.responses.create(model=os.environ['AZURE_OPENAI_MODEL'], input='Reply with exactly: AZURE_OPENAI_TEST_OK'); print(r.output_text)"
                    '''
                }
            }
        }

        stage('Install AI Dependencies') {
            steps {
                bat 'python -m pip install --disable-pip-version-check -r requirements.txt'
            }
        }

        stage('Terraform Init') {
            steps {
                dir("${TF_DIR}") {
                    bat 'terraform init -input=false'
                }
            }
        }

        stage('Reset Local Test State') {
            steps {
                // This project is intentionally local-only for MVP-2.
                // Destroying the local test state makes every build deterministic
                // and does not touch Azure/AWS.
                //
                // NEVER use this stage in a production pipeline.
                dir("${TF_DIR}") {
                    bat 'terraform destroy -auto-approve -input=false'
                }
            }
        }

        stage('Terraform Validate') {
            steps {
                dir("${TF_DIR}") {
                    bat 'terraform validate'
                }
            }
        }

        stage('Terraform Plan') {
            steps {
                dir("${TF_DIR}") {
                    bat 'terraform plan -out=tfplan'
                }
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

                    int rc = bat(
                        script: 'cd terraform && terraform apply -auto-approve tfplan > ..\\terraform-apply.log 2>&1',
                        returnStatus: true
                    )

                    if (rc != 0) {
                        env.TERRAFORM_APPLY_FAILED = 'true'
                        currentBuild.description =
                            'Terraform apply failed - AI remediation started'

                        echo 'Terraform Apply failed. Continuing to AI remediation.'
                    } else {
                        env.TERRAFORM_APPLY_FAILED = 'false'
                    }
                }
            }
        }

        stage('AI Remediation') {
            when {
                expression {
                    env.TERRAFORM_APPLY_FAILED == 'true'
                }
            }

            steps {
                script {

                    withCredentials([
                        string(
                            credentialsId: 'azure-openai-api-key',
                            variable: 'AZURE_OPENAI_API_KEY'
                        )
                    ]) {

                        int rc = bat(
                            script: 'python agent\\ai_remediate.py --workspace terraform --log terraform-apply.log > ai-remediation.json',
                            returnStatus: true
                        )

                        archiveArtifacts(
                            artifacts: 'ai-remediation.json,terraform-apply.log',
                            fingerprint: true
                        )

                        if (rc != 0) {
                            error(
                                'AI agent did not produce a validated safe remediation'
                            )
                        }
                    }
                }
            }
        }

        stage('Re-Apply After AI Fix') {
            when {
                expression {
                    env.TERRAFORM_APPLY_FAILED == 'true' &&
                    fileExists('terraform/ai-remediation.tfplan')
                }
            }

            steps {
                script {

                    int rc = bat(
                        script: 'cd terraform && terraform apply -auto-approve ai-remediation.tfplan',
                        returnStatus: true
                    )

                    if (rc != 0) {
                        error(
                            'AI remediation validation/plan succeeded, but re-apply failed'
                        )
                    }

                    env.TERRAFORM_APPLY_FAILED = 'false'

                    currentBuild.description =
                        'Deployment recovered by AI remediation'
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts(
                artifacts: 'terraform-apply.log,ai-remediation.json',
                allowEmptyArchive: true,
                fingerprint: true
            )
        }
    }
}
