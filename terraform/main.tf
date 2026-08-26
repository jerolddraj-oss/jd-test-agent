terraform {
  required_version = ">= 1.5.0"

  required_providers {
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}

provider "local" {}

variable "deployment_name" {
  type    = string
  default = "agentic-mvp"
}

locals {
  output_path = "${path.module}/generated/${var.deployment_name}.txt"
}

# MVP-1 intentionally contains a valid Terraform configuration that fails
# during APPLY. The invalid argument is not caught by init/validate/plan in
# this test harness because the failure is produced by the helper script.
resource "local_file" "deployment" {
  filename = local.output_path
  content  = "deployment=${var.deployment_name}\n"
}

output "deployment_file" {
  value = local_file.deployment.filename
}
