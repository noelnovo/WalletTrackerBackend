variable "db_hostname" {
  description = "MariaDB container hostname"
  type        = string
  default     = "database.wallettracker.downops.win"
}
variable "wallettracker_mariadb_database" {
  description = "Database name to initialize"
  type        = string
  default     = "wallet_tracker"
}
variable "db_volume" {
  description = "Host directory to bind-mount as /var/lib/mysql"
  type        = string
  default     = "/mnt/mariadb_wallettracker_v2"
}
variable "storage_name" {
  description = "Rootfs storage for container"
  type        = string
  default     = "local-lvm"
}

resource "null_resource" "ensure_mariadb_volume" {
  triggers = {
    db_volume = var.db_volume
  }
  connection {
    type     = "ssh"
    user     = data.vault_kv_secret_v2.proxmox.data["PROXMOX_USER"]
    host     = var.proxmox_ip
    password = data.vault_kv_secret_v2.proxmox.data["PROXMOX_PASSWORD"]
  }
  provisioner "remote-exec" {
    inline = [
      "if [ ! -d '${var.db_volume}' ]; then",
      "  echo 'Creating MariaDB data directory at ${var.db_volume}...'",
      "  mkdir -p '${var.db_volume}'",
      "  chmod 770 '${var.db_volume}'",
      "  chown 100100:100101 '${var.db_volume}'",
      "else",
      "  echo 'Directory ${var.db_volume} already exists.'",
      "fi"
    ]
  }
}

resource "proxmox_lxc" "mariadb" {
  depends_on  = [null_resource.ensure_mariadb_volume]
  target_node = var.target_node
  hostname    = var.db_hostname
  ostemplate  = "local:vztmpl/alpine-3.22-default_20250617_amd64.tar.xz"
  password    = data.vault_kv_secret_v2.app.data["DB_CONTAINER_PASSWORD"]
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
    gw     = "10.2.0.1"
    ip     = "${var.db_container_ip}/24"
  }
  mountpoint {
    key     = "1"
    slot    = "1"
    storage = var.db_volume
    volume  = var.db_volume
    mp      = "/var/lib/mysql"
    size    = "10G"
  }
  start = true
  lifecycle {
    prevent_destroy = true
  }
}

resource "null_resource" "setup_mariadb_in_container" {
  depends_on = [proxmox_lxc.mariadb]

  connection {
    type     = "ssh"
    host     = var.proxmox_ip
    user     = data.vault_kv_secret_v2.proxmox.data["PROXMOX_USER"]
    password = data.vault_kv_secret_v2.proxmox.data["PROXMOX_PASSWORD"]
  }

  provisioner "remote-exec" {
    inline = [
      <<-EOF
      set -eu
      pct exec ${proxmox_lxc.mariadb.vmid} -- apk update
      pct exec ${proxmox_lxc.mariadb.vmid} -- apk add gettext mariadb mariadb-client

      # Existing native account state is authoritative. Never reset a role here.
      if ! pct exec ${proxmox_lxc.mariadb.vmid} -- test -d /var/lib/mysql/mysql; then
        echo "Fresh MariaDB requires separately approved native initialization/account bootstrap; refusing password fallback." >&2
        exit 1
      fi
      pct exec ${proxmox_lxc.mariadb.vmid} -- rc-service mariadb status
      test "$(pct exec ${proxmox_lxc.mariadb.vmid} -- mariadb -Nse "SELECT COUNT(*) FROM mysql.global_priv WHERE User='root' AND Host='${var.api_container_ip}'")" = "1"

      EOF
    ]
  }
}

resource "null_resource" "deploy_mariadb" {
  depends_on = [null_resource.setup_mariadb_in_container]

  triggers = {
    source_revision = var.source_revision
  }

  connection {
    type     = "ssh"
    host     = var.proxmox_ip
    user     = data.vault_kv_secret_v2.proxmox.data["PROXMOX_USER"]
    password = data.vault_kv_secret_v2.proxmox.data["PROXMOX_PASSWORD"]
  }

  provisioner "remote-exec" {
    inline = [
      <<-EOF
      set -eu
      # Read-only guard on each release. New or missing accounts fail closed.
      pct exec ${proxmox_lxc.mariadb.vmid} -- test -d /var/lib/mysql/mysql
      test "$(pct exec ${proxmox_lxc.mariadb.vmid} -- mariadb -Nse "SELECT COUNT(*) FROM mysql.global_priv WHERE User='root' AND Host='${var.api_container_ip}'")" = "1"

      EOF
    ]
  }
}

output "mariadb_container" {
  value = proxmox_lxc.mariadb.hostname
}
