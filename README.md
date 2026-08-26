# Agentic Terraform CI/CD — MVP-1

A reference implementation of an Agentic AI remediation loop for Jenkins + Terraform.

## MVP-1 goal

Simulate the real deployment failure pattern:

1. `terraform init` passes
2. `terraform validate` passes
3. `terraform plan` passes
4. `terraform apply` fails
5. Remediation agent reads the failure and workspace
6. Agent produces a controlled code fix
7. Terraform is formatted and validated again
8. A new plan is generated
9. The pipeline can retry apply

The MVP uses a local Terraform test scenario so the remediation loop can be developed safely before connecting Azure credentials.

## Architecture

```text
GitHub
  |
  v
Jenkins
  |
  +--> terraform init
  +--> terraform validate
  +--> terraform plan
  +--> approval
  +--> terraform apply
          |
          +-- failure --> remediation agent
                           |
                           +--> collect logs
                           +--> inspect .tf files
                           +--> classify error
                           +--> create patch
                           +--> fmt/validate/plan
                           +--> retry apply
```

## Safety boundary

The MVP agent never edits the protected Git branch. Remediation happens in the Jenkins workspace. The pipeline limits remediation attempts and fails closed when the agent cannot prove a safe fix.

## Next phase

Connect the tool layer to Azure Monitor, Azure CLI/SDK, Git diff, real Terraform modules, and an LLM/agent runtime such as Microsoft Foundry Agent Service.