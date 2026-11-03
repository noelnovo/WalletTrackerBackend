variable "proxmox_ssh_identity_file" {
  description = "Protected job-time private key file rendered from Vault; never commit it"
  type        = string
}

variable "proxmox_ssh_host_key" {
  description = "Trusted Proxmox SSH host public key obtained through the existing management channel"
  type        = string
  validation {
    condition     = can(regex("^ssh-ed25519 ", var.proxmox_ssh_host_key))
    error_message = "A verified Proxmox ed25519 host public key is required."
  }
}

variable "source_revision" {
  description = "Exact tested Git commit to deploy; supplied by Jenkins"
  type        = string
  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.source_revision))
    error_message = "source_revision must be a full immutable Git commit SHA."
  }
}

variable "vault_addr" {
  description = "Vault server address"
  type        = string
  default     = "https://vault.int.downops.win"
}

variable "vault_kv_mount" {
  description = "Vault KV v2 mount where project secrets are stored"
  type        = string
  default     = "downops"
}

variable "vault_kv_proxmox_secret_path" {
  description = "Path under the Vault KV v2 mount holding Proxmox credentials"
  type        = string
  default     = "services/proxmox/terraform"
}

variable "vault_kv_cloudflare_secret_path" {
  description = "Path under the Vault KV v2 mount holding Cloudflare credentials"
  type        = string
  default     = "services/cloudflare/account-api"
}

variable "vault_kv_app_secret_path" {
  description = "Minimal infrastructure-only KV: BACKEND_CONTAINER_PASSWORD, DB_CONTAINER_PASSWORD, CLOUDFLARE_ZONE_ID"
  type        = string
  default     = "apps/wallettracker/infrastructure"
}


variable "proxmox_ip" {
  description = "Proxmox IP address"
  type        = string
  default     = "proxmox.int.downops.win"
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
