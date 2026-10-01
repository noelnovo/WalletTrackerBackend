variable "vault_addr" {
  description = "Vault server address"
  type        = string
  default     = "https://vault.downops.win"
}

variable "vault_kv_mount" {
  description = "Vault KV v2 mount where project secrets are stored"
  type        = string
  default     = "downops"
}

variable "vault_kv_common_secret_path" {
  description = "Path under the Vault KV v2 mount holding shared/common infrastructure secrets"
  type        = string
  default     = "common"
}

variable "vault_kv_app_secret_path" {
  description = "Path under the Vault KV v2 mount holding app-specific secrets"
  type        = string
  default     = "wallettracker.backend"
}

variable "vault_kv_app_common_secret_path" {
  description = "Path under the Vault KV v2 mount holding app-shared secrets"
  type        = string
  default     = "wallettracker.common"
}

variable "proxmox_ip" {
  description = "Proxmox IP address"
  type        = string
  default     = "192.168.0.20"
}
variable "proxmox_port" {
  description = "Proxmox port number"
  type        = string
  default     = "8006"
}
variable "target_node" {
  description = "Proxmox node name"
  type        = string
  default     = "proxmoxserver"
}
variable "bridge_name" {
  description = "Network bridge"
  type        = string
  default     = "vmbr0"
}
variable "api_container_ip" {
  description = "API container IP address"
  type        = string
  default     = "10.2.0.201"
}
variable "db_container_ip" {
  description = "MariaDB container IP address"
  type        = string
  default     = "10.2.0.202"
}
