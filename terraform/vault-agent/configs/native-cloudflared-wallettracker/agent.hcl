log_level = "warn"
disable_mlock = true
vault { address = "https://vault.int.downops.win" }
auto_auth {
  method "approle" {
    config = {
      role_id_file_path = "/etc/vault-agent/native-cloudflared-wallettracker/auth/role_id"
      secret_id_file_path = "/etc/vault-agent/native-cloudflared-wallettracker/auth/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }
}
template_config {
  static_secret_render_interval = "1m"
  exit_on_retry_failure = true
}
env_template "TUNNEL_TOKEN" {
  contents = "{{ with secret \"downops/data/services/cloudflared/wallettracker\" }}{{ .Data.data.TUNNEL_TOKEN }}{{ end }}"
  error_on_missing_key = true
}
exec {
  command = ["/usr/bin/cloudflared", "tunnel", "run"]
  restart_on_secret_changes = "always"
  restart_stop_signal = "SIGTERM"
}
