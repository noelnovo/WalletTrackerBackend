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
  program = [
    "bash", "-lc",
    <<-EOT
      set -euo pipefail
      account_id='${data.vault_kv_secret_v2.cloudflare.data["CLOUDFLARE_ACCOUNT_ID"]}'
      token='${data.vault_kv_secret_v2.cloudflare.data["CLOUDFLARE_API_TOKEN"]}'

      if [ -z "$account_id" ] || [ -z "$token" ]; then
        echo '{"exists":"false","tunnel_id":""}'
        exit 0
      fi

      response=$(curl -fsS \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        "https://api.cloudflare.com/client/v4/accounts/$account_id/cfd_tunnel")

      exists=$(printf '%s' "$response" | python3 -c 'import json,sys; data=json.load(sys.stdin); print("true" if any(item.get("name") == "wallettracker-api" for item in data.get("result", [])) else "false")')
      tunnel_id=$(printf '%s' "$response" | python3 -c 'import json,sys; data=json.load(sys.stdin); print(next((item.get("id", "") for item in data.get("result", []) if item.get("name") == "wallettracker-api"), ""))')

      printf '{"exists":"%s","tunnel_id":"%s"}\n' "$exists" "$tunnel_id"
    EOT
  ]
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
    type     = "ssh"
    host     = var.proxmox_ip
    user     = data.vault_kv_secret_v2.proxmox.data["PROXMOX_USER"]
    password = data.vault_kv_secret_v2.proxmox.data["PROXMOX_PASSWORD"]
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
