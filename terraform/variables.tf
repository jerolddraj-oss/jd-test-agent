variable "location" {
  description = "Azure region for the test deployment"
  type        = string
  default     = "eastus"
}

variable "admin_username" {
  description = "Local administrator username for both VMs"
  type        = string
  default     = "azureadmin"
}

variable "admin_password" {
  description = "Local administrator password for both VMs"
  type        = string
  sensitive   = true
}

variable "resource_group_name" {
  description = "Resource group used by the Terraform test"
  type        = string
  default     = "rg-agentic-terraform-mvp"
}
