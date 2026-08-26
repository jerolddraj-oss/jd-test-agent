# Agentic Terraform CI/CD — MVP-2

A Jenkins + Terraform closed-loop remediation prototype with an Azure OpenAI/Foundry model responsible for diagnosis and patch generation.

## MVP-2 flow

1. `terraform init` passes
2. `terraform validate` passes
3. `terraform plan` passes
4. Human approval
5. `terraform apply` fails
6. Jenkins captures the failure log
7. AI receives the failure log, Terraform/YAML/JSON workspace files, and Git diff
8. AI returns a structured root-cause diagnosis and minimal patch proposal
9. Deterministic safety gates validate the proposal
10. The patch is applied only inside the temporary Jenkins workspace
11. `terraform fmt`, `terraform validate`, and `terraform plan` run
12. Only a successful validation/plan can reach re-apply

## Architecture

```text
GitHub
  |
  v
Jenkins / Windows-Agent
  |
  +--> Terraform init/validate/plan
  +--> Human approval
  +--> Terraform apply
          |
          +-- failure --> AI remediation agent
                           |
                           +--> failure log
                           +--> workspace code
                           +--> git diff
                           +--> Azure OpenAI / Foundry model
                           +--> structured patch
                           +--> safety policy
                           +--> fmt/validate/plan
                           +--> re-apply
```

## Configure Jenkins

Create a Jenkins **Secret text** credential with ID:

`azure-openai-api-key`

Set these non-secret environment variables on the Windows-Agent or in Jenkins global environment configuration:

- `AZURE_OPENAI_ENDPOINT` — e.g. `https://<resource-name>.openai.azure.com`
- `AZURE_OPENAI_MODEL` — the deployed model name

Do not commit an API key to GitHub.

The current implementation uses the Azure OpenAI v1 Responses API through the OpenAI Python client. Microsoft recommends Microsoft Entra ID for authentication in production; API-key authentication is used in this MVP to simplify the first Jenkins integration.

## Safety boundary

The model cannot execute shell commands. It only proposes a structured patch. The local safety layer enforces:

- workspace-only paths
- allowed file extensions
- exact `old_text` matching
- minimum confidence of 0.85
- LOW risk for automatic remediation
- rejection of known IAM/RBAC, credential, security, database, and destroy operations
- Terraform fmt/validate/plan must all pass before re-apply

The Git branch is not modified by the remediation process.

## Next phase

MVP-3 will add real Azure investigation tools (Azure Monitor/Log Analytics, resource health, AKS/App Service state) and then AWS CloudWatch/SSM tools. The same safety layer remains outside the model.
