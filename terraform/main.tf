terraform {
  required_version = ">= 1.5.0"

  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "local" {}
provider "null" {}

variable "deployment_name" {
  type    = string
  default = "agentic-mvp"
}

locals {
  output_path = "${path.module}/generated/${var.deployment_name}.txt"
}

resource "local_file" "deployment" {
  filename = local.output_path
  content  = "deployment=${var.deployment_name}\n"
}

# Intentionally broken for MVP-1. init/validate/plan pass, but apply fails
# because the provisioner exits non-zero. The remediation agent is expected
# to replace the failing command with a safe success condition in the
# temporary Jenkins workspace, then re-run validation/plan/apply.
resource "null_resource" "deployment_gate" {
  triggers = {
    deployment_file = local_file.deployment.id
  }

  provisioner "local-exec" {
    command = "test -f ${path.module}/generated/THIS_FILE_DOES_NOT_EXIST.txt"
  }
}

output "deployment_file" {
  value = local_file.deployment.filename
}
