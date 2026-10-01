variable "api_public_hostname" {
  description = "Public hostname for the API (e.g. api.downops.win)"
  type        = string
  default     = "api.downops.win"
}

locals {
  cloudflare_tunnel_name = "wallettracker-api"
  api_tunnel_id = try(cloudflare_zero_trust_tunnel_cloudflared.api[0].id, data.external.cloudflare_tunnel_api_exists.result.tunnel_id)
}

data "external" "cloudflare_tunnel_api_exists" {
  program = [
    "bash", "-lc",
    <<-EOT
      set -euo pipefail
      account_id='${data.vault_kv_secret_v2.common.data["CLOUDFLARE_ACCOUNT_ID"]}'
      token='${data.vault_kv_secret_v2.common.data["CLOUDFLARE_API_TOKEN"]}'

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
  account_id = data.vault_kv_secret_v2.common.data["CLOUDFLARE_ACCOUNT_ID"]
  name       = local.cloudflare_tunnel_name
  depends_on = [null_resource.deploy_api]
}

data "cloudflare_zero_trust_tunnel_cloudflared_token" "api" {
  account_id = data.vault_kv_secret_v2.common.data["CLOUDFLARE_ACCOUNT_ID"]
  tunnel_id  = local.api_tunnel_id
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "api" {
  account_id = data.vault_kv_secret_v2.common.data["CLOUDFLARE_ACCOUNT_ID"]
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
    user     = data.vault_kv_secret_v2.common.data["PROXMOX_USER"]
    password = data.vault_kv_secret_v2.common.data["PROXMOX_PASSWORD"]
  }

  provisioner "file" {
    content     = <<-INITEOF
      #!/sbin/openrc-run
      name="cloudflared"
      description="Cloudflare Tunnel"
      command="/usr/bin/cloudflared"
      command_args="tunnel run --token ${data.cloudflare_zero_trust_tunnel_cloudflared_token.api.token}"
      command_background=true
      supervise_daemon="yes"
      pidfile="/run/cloudflared.pid"
      output_log="/var/log/cloudflared.log"
      error_log="/var/log/cloudflared.log"

      depend() {
        need net
        after wallettracker
      }
      INITEOF
    destination = "/tmp/cloudflared.init"
  }

  provisioner "remote-exec" {
    inline = [
      <<-EOF
      pct exec ${proxmox_lxc.api.vmid} -- wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O /usr/bin/cloudflared
      pct exec ${proxmox_lxc.api.vmid} -- chmod +x /usr/bin/cloudflared

      pct push ${proxmox_lxc.api.vmid} /tmp/cloudflared.init /etc/init.d/cloudflared
      rm /tmp/cloudflared.init

      pct exec ${proxmox_lxc.api.vmid} -- chmod +x /etc/init.d/cloudflared
      pct exec ${proxmox_lxc.api.vmid} -- rc-update add cloudflared default
      pct exec ${proxmox_lxc.api.vmid} -- rc-service cloudflared start
      EOF
    ]
  }
}

output "api_public_url" {
  value = "https://${var.api_public_hostname}"
}
