variable "api_public_hostname" {
  description = "Public hostname for the API (e.g. api.downops.win)"
  type        = string
  default     = "api.downops.win"
}

locals {
  cloudflare_tunnel_name = "wallettracker-api"
  api_tunnel_id          = try(cloudflare_zero_trust_tunnel_cloudflared.api[0].id, data.external.cloudflare_tunnel_api_exists.result.tunnel_id)
}

data "external" "cloudflare_tunnel_api_exists" {
  program = ["python3", "${path.module}/find_tunnel.py"]
  query = {
    account_id = data.vault_kv_secret_v2.cloudflare.data["CLOUDFLARE_ACCOUNT_ID"]
    token      = data.vault_kv_secret_v2.cloudflare.data["CLOUDFLARE_API_TOKEN"]
  }
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "api" {
  count      = data.external.cloudflare_tunnel_api_exists.result.exists == "true" ? 0 : 1
  account_id = data.vault_kv_secret_v2.cloudflare.data["CLOUDFLARE_ACCOUNT_ID"]
  name       = local.cloudflare_tunnel_name
  depends_on = [null_resource.deploy_api]
}

# Connector credentials are consumed only by native Vault Agent, never Terraform.

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "api" {
  account_id = data.vault_kv_secret_v2.cloudflare.data["CLOUDFLARE_ACCOUNT_ID"]
  tunnel_id  = local.api_tunnel_id

  config = {
    ingress = [
      {
        hostname = var.api_public_hostname
        service  = "http://localhost:5000"
      },
      {
        service = "http_status:404"
      }
    ]
  }
}

resource "cloudflare_dns_record" "api" {
  zone_id = data.vault_kv_secret_v2.app.data["CLOUDFLARE_ZONE_ID"]
  name    = "api"
  content = "${local.api_tunnel_id}.cfargotunnel.com"
  type    = "CNAME"
  ttl     = 1
  proxied = true
  lifecycle {
    create_before_destroy = false
  }
}

resource "null_resource" "setup_cloudflared" {
  depends_on = [null_resource.deploy_api, cloudflare_zero_trust_tunnel_cloudflared.api]

  connection {
    type        = "ssh"
    host        = var.proxmox_ip
    user        = data.vault_kv_secret_v2.proxmox.data["PROXMOX_USER"]
    private_key = file(var.proxmox_ssh_identity_file)
    host_key    = var.proxmox_ssh_host_key
    agent       = false
  }

  provisioner "remote-exec" {
    inline = ["install -d -m 0700 ${local.delivery_dir}"]
  }
  provisioner "file" {
    source      = "${path.module}/vault-agent/"
    destination = local.delivery_dir
  }
  provisioner "remote-exec" {
    # Existing binary and protected AppRole bootstrap must already be present.
    # An absent start marker fails closed, not an implicit provider/tunnel repair.
    inline = ["python3 ${local.delivery_dir}/install.py install-tunnel --guest ${proxmox_lxc.api.vmid}"]
  }
}

output "api_public_url" {
  value = "https://${var.api_public_hostname}"
}
