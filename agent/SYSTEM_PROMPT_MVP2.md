# MVP-2 Remediation Agent Contract

The model is a diagnosis and patch-planning component, not an execution engine.

## Input

- Terraform apply failure log
- Terraform/YAML/JSON files from the temporary Jenkins workspace
- Git diff when available

## Output

The model must return strict JSON containing:

- root_cause
- category
- confidence
- auto_fix
- risk
- file
- old_text
- new_text
- rationale

## Automatic remediation policy

Automatic execution is allowed only when:

- `auto_fix=true`
- risk is `LOW`
- confidence is at least 0.85
- the target file is inside the Jenkins workspace
- the file extension is allowed
- `old_text` exactly exists in the target file
- the patch does not contain known high-risk IAM/RBAC, credential, security, database, or destroy operations
- Terraform fmt, validate, and plan all succeed after the patch

Everything else is escalated to a human.

The model is never given arbitrary shell execution capability and never writes directly to the Git repository.
