variable "api_hostname" {
  description = "API container hostname"
  type        = string
  default     = "backend.wallettracker.downops.win"
}

locals {
  repo_path = "/srv/WalletTrackerAPI"
  api_vmid  = proxmox_lxc.api.vmid

  wallettracker_init = <<-INITEOF
    #!/sbin/openrc-run
    description="WalletTracker uWSGI"

    directory="${local.repo_path}/app"
    pidfile="/run/wallettracker.pid"
    command="/srv/WalletTrackerAPI/app/.venv/bin/uwsgi"
    command_args="--ini $${directory}/uwsgi.ini --logto2 /var/log/wallettracker.log"
    command_background="yes"

    export DATABASE_ROOT_PASSWORD="${data.vault_kv_secret_v2.app.data["MARIADB_ROOT_PASSWORD"]}"
    export WALLET_TRACKER_DB_USER="root"
    export WALLET_TRACKER_DB_HOST="${var.db_container_ip}"
    export DATABASE_NAME="wallet_tracker"
    export WALLET_TRACKER_SECRET="${data.vault_kv_secret_v2.app_common.data["SIGN_SECRET_WORD"]}"
    export ENABLE_REGISTER="false"

    start_pre() {
      checkpath --directory --owner root:root $${pidfile%/*}
    }
  INITEOF
}

resource "proxmox_lxc" "api" {
  target_node = var.target_node
  hostname    = var.api_hostname
  ostemplate  = "local:vztmpl/alpine-3.22-default_20250617_amd64.tar.xz"
  password    = data.vault_kv_secret_v2.app.data["BACKEND_CONTAINER_PASSWORD"]
  cores       = 1
  memory      = 512
  swap        = 512
  nameserver  = "8.8.8.8"
  rootfs {
    storage = "local-lvm"
    size    = "4G"
  }
  network {
    name   = "eth0"
    bridge = var.bridge_name
    gw     = "192.168.0.1"
    ip     = "${var.api_container_ip}/24"
  }
  start = true
  lifecycle {
    create_before_destroy = true
  }
}

resource "null_resource" "setup_api_in_container" {
  depends_on = [proxmox_lxc.api]

  connection {
    type     = "ssh"
    host     = var.proxmox_ip
    user     = data.vault_kv_secret_v2.common.data["PROXMOX_USER"]
    password = data.vault_kv_secret_v2.common.data["PROXMOX_PASSWORD"]
  }

  provisioner "file" {
    content     = local.wallettracker_init
    destination = "/tmp/wallettracker.init"
  }

  provisioner "remote-exec" {
    inline = [
      <<-EOF
      set -ex
      pct exec ${local.api_vmid} -- apk update
      pct exec ${local.api_vmid} -- sh -c "apk add --no-cache git python3 py3-pip mariadb-dev gcc musl-dev python3-dev build-base linux-headers uv"

      pct exec ${local.api_vmid} -- rm -rf ${local.repo_path}
      pct exec ${local.api_vmid} -- git clone https://github.com/noelnovo/WalletTrackerBackend.git ${local.repo_path}

      pct exec ${local.api_vmid} -- uv sync --no-dev --no-install-project --project ${local.repo_path}/app

      pct exec ${local.api_vmid} -- apk del gcc musl-dev build-base linux-headers

      pct exec ${local.api_vmid} -- touch /var/log/wallettracker.log
      pct exec ${local.api_vmid} -- chmod 644 /var/log/wallettracker.log

      pct push ${local.api_vmid} /tmp/wallettracker.init /etc/init.d/wallettracker
      rm /tmp/wallettracker.init

      pct exec ${local.api_vmid} -- chmod +x /etc/init.d/wallettracker
      pct exec ${local.api_vmid} -- rc-update add wallettracker default
      pct exec ${local.api_vmid} -- rc-service wallettracker start
      EOF
    ]
  }
}

resource "null_resource" "deploy_api" {
  depends_on = [null_resource.setup_api_in_container, null_resource.deploy_mariadb]

  triggers = {
    always_run = timestamp()
  }

  connection {
    type     = "ssh"
    host     = var.proxmox_ip
    user     = data.vault_kv_secret_v2.common.data["PROXMOX_USER"]
    password = data.vault_kv_secret_v2.common.data["PROXMOX_PASSWORD"]
  }

  provisioner "remote-exec" {
    inline = [
      <<-EOF
      set -ex
      pct exec ${local.api_vmid} -- git -C ${local.repo_path} pull

      pct exec ${local.api_vmid} -- uv sync --no-dev --no-install-project --project ${local.repo_path}/app

      pct exec ${local.api_vmid} -- sh -c "export DATABASE_ROOT_PASSWORD='${data.vault_kv_secret_v2.app.data["MARIADB_ROOT_PASSWORD"]}'; export DATABASE_NAME='wallet_tracker'; export WALLET_TRACKER_DB_USER='root'; export WALLET_TRACKER_DB_HOST='${var.db_container_ip}'; ${local.repo_path}/app/.venv/bin/python ${local.repo_path}/app/migrate_all.py"

      pct exec ${local.api_vmid} -- rc-service wallettracker restart
      EOF
    ]
  }
}

output "api_container" {
  value = proxmox_lxc.api.hostname
}
