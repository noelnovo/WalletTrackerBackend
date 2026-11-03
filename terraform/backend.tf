variable "api_hostname" {
  description = "API container hostname"
  type        = string
  default     = "backend.wallettracker.downops.win"
}

locals {
  repo_path = "/srv/WalletTrackerAPI"
  api_vmid  = proxmox_lxc.api.vmid

  delivery_dir = "/var/lib/wallettracker-delivery/${local.api_vmid}"
}

resource "proxmox_lxc" "api" {
  target_node = var.target_node
  hostname    = var.api_hostname
  ostemplate  = "local:vztmpl/alpine-3.22-default_20250617_amd64.tar.xz"
  password    = data.vault_kv_secret_v2.api_root_password.data["ROOT_PASSWORD"]
  cores       = 1
  memory      = 512
  swap        = 512
  nameserver  = "10.2.0.4"
  rootfs {
    storage = "local-lvm"
    size    = "4G"
  }
  network {
    name   = "eth0"
    bridge = var.bridge_name
    gw     = "10.2.0.1"
    ip     = "${var.api_container_ip}/24"
  }
  onboot = true
  start  = true
  lifecycle {
    prevent_destroy = true
  }
}

resource "null_resource" "setup_api_in_container" {
  depends_on = [proxmox_lxc.api]

  connection {
    type        = "ssh"
    host        = var.proxmox_ip
    user        = data.vault_kv_secret_v2.proxmox.data["PROXMOX_USER"]
    private_key = file(var.proxmox_ssh_identity_file)
    host_key    = var.proxmox_ssh_host_key
    agent       = false
    timeout     = "30s"
  }


  provisioner "remote-exec" {
    inline = [
      <<-EOF
      set -eu
      pct exec ${local.api_vmid} -- apk update
      pct exec ${local.api_vmid} -- sh -c "apk add --no-cache git python3 py3-pip mariadb-dev gcc musl-dev python3-dev build-base linux-headers uv"

      if ! pct exec ${local.api_vmid} -- test -d ${local.repo_path}/.git; then
        pct exec ${local.api_vmid} -- git clone https://github.com/noelnovo/WalletTrackerBackend.git ${local.repo_path}
      fi

      pct exec ${local.api_vmid} -- git -C ${local.repo_path} fetch origin
      pct exec ${local.api_vmid} -- git -C ${local.repo_path} checkout --detach ${var.source_revision}
      pct exec ${local.api_vmid} -- uv sync --frozen --no-dev --no-install-project --project ${local.repo_path}/app

      pct exec ${local.api_vmid} -- apk del gcc musl-dev build-base linux-headers

      pct exec ${local.api_vmid} -- touch /var/log/wallettracker.log
      pct exec ${local.api_vmid} -- chmod 644 /var/log/wallettracker.log

      install -d -m 0700 ${local.delivery_dir}
      EOF
    ]
  }
  provisioner "file" {
    source      = "${path.module}/vault-agent/"
    destination = local.delivery_dir
  }
  provisioner "remote-exec" {
    inline = ["python3 ${local.delivery_dir}/install.py install-api --guest ${local.api_vmid} --db-host ${var.db_container_ip}"]
  }
}

resource "null_resource" "deploy_api" {
  depends_on = [null_resource.setup_api_in_container, null_resource.deploy_mariadb]

  triggers = {
    source_revision = var.source_revision
    delivery_assets = sha256(join("", [for f in sort(tolist(fileset("${path.module}/vault-agent", "**"))) : filesha256("${path.module}/vault-agent/${f}")]))
  }

  connection {
    type        = "ssh"
    host        = var.proxmox_ip
    user        = data.vault_kv_secret_v2.proxmox.data["PROXMOX_USER"]
    private_key = file(var.proxmox_ssh_identity_file)
    host_key    = var.proxmox_ssh_host_key
    agent       = false
    timeout     = "30s"
  }

  provisioner "remote-exec" {
    inline = ["install -d -m 0700 ${local.delivery_dir}"]
  }
  provisioner "file" {
    source      = "${path.module}/vault-agent/"
    destination = local.delivery_dir
  }
  provisioner "remote-exec" {
    inline = [
      <<-EOF
      set -eu
      # Refuse to discard local edits (including untracked private inputs).
      test -z "$(pct exec ${local.api_vmid} -- git -C ${local.repo_path} status --porcelain --untracked-files=no)"
      pct exec ${local.api_vmid} -- git -C ${local.repo_path} fetch origin
      # Deploy exactly the revision tested/built by Jenkins, not whichever main
      # happens to be newest when this provisioner starts.
      pct exec ${local.api_vmid} -- git -C ${local.repo_path} checkout --detach ${var.source_revision}

      # mysqlclient has no musl wheel and must compile from source. setup_api_in_container
      # removes the toolchain after the first install and is not re-run on existing
      # containers, so make sure a compiler is available before every uv sync. This is a
      # no-op once the toolchain is already present.
      pct exec ${local.api_vmid} -- sh -c 'command -v cc >/dev/null 2>&1 || apk add --no-cache build-base mariadb-dev python3-dev'

      pct exec ${local.api_vmid} -- uv sync --frozen --no-dev --no-install-project --project ${local.repo_path}/app

      python3 ${local.delivery_dir}/install.py install-api --guest ${local.api_vmid} --db-host ${var.db_container_ip}
      python3 ${local.delivery_dir}/install.py migrate --guest ${local.api_vmid} --db-guest ${proxmox_lxc.mariadb.vmid} --db-host ${var.db_container_ip}
      python3 ${local.delivery_dir}/install.py verify --guest ${local.api_vmid}

      EOF
    ]
  }
}

output "api_container" {
  value = proxmox_lxc.api.hostname
}
