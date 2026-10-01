terraform {
  required_providers {
    proxmox = {
      source  = "Telmate/proxmox"
      version = "3.0.2-rc07"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.19.1"
    }
    vault = {
      source  = "hashicorp/vault"
      version = "~> 5.9"
    }
  }
}

provider "vault" {
  address           = var.vault_addr
  skip_child_token  = true
}

data "vault_kv_secret_v2" "common" {
  mount = var.vault_kv_mount
  name  = var.vault_kv_common_secret_path
}

data "vault_kv_secret_v2" "app" {
  mount = var.vault_kv_mount
  name  = var.vault_kv_app_secret_path
}

data "vault_kv_secret_v2" "app_common" {
  mount = var.vault_kv_mount
  name  = var.vault_kv_app_common_secret_path
}

provider "cloudflare" {
  api_token = data.vault_kv_secret_v2.common.data["CLOUDFLARE_API_TOKEN"]
}

provider "proxmox" {
  pm_api_url      = "https://${var.proxmox_ip}:${var.proxmox_port}/api2/json"
  pm_user         = "${data.vault_kv_secret_v2.common.data["PROXMOX_USER"]}@pam"
  pm_password     = data.vault_kv_secret_v2.common.data["PROXMOX_PASSWORD"]
  pm_tls_insecure = true
}
