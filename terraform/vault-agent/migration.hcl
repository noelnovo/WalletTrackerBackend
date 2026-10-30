log_level = "warn"
disable_mlock = true
vault { address = "https://vault.int.downops.win" }
auto_auth {
  method "approle" {
    config = {
      role_id_file_path = "/etc/vault-agent/native-wallettracker-api/auth/role_id"
      secret_id_file_path = "/etc/vault-agent/native-wallettracker-api/auth/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }
}
template_config {
  static_secret_render_interval = "1m"
  exit_on_retry_failure = true
}
env_template "PATH" {
  contents = "/bin:/sbin:/usr/bin:/usr/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin"
  error_on_missing_key = true
}
env_template "DATABASE_ROOT_PASSWORD" {
  contents = "{{ with secret \"downops/data/apps/wallettracker/runtime\" }}{{ .Data.data.DATABASE_ROOT_PASSWORD }}{{ end }}"
  error_on_missing_key = true
}
env_template "WALLET_TRACKER_SECRET" {
  contents = "{{ with secret \"downops/data/apps/wallettracker/runtime\" }}{{ .Data.data.WALLET_TRACKER_SECRET }}{{ end }}"
  error_on_missing_key = true
}
env_template "PRIVATE_KEY_BASE64" {
  contents = "{{ with secret \"downops/data/apps/wallettracker/rsa\" }}{{ .Data.data.PRIVATE_KEY_BASE64 }}{{ end }}"
  error_on_missing_key = true
}
env_template "PUBLIC_KEY_BASE64" {
  contents = "{{ with secret \"downops/data/apps/wallettracker/rsa\" }}{{ .Data.data.PUBLIC_KEY_BASE64 }}{{ end }}"
  error_on_missing_key = true
}
exec {
  command = ["/srv/WalletTrackerAPI/app/.venv/bin/python", "/etc/vault-agent/native-wallettracker-api/config/render-rsa.py", "--identity-file", "/etc/vault-agent/native-wallettracker-api/config/rsa-identity.json", "--app-dir", "/srv/WalletTrackerAPI/app", "--runtime-dir", "/run/vault-agent-native-wallettracker-api/rsa", "--", "/srv/WalletTrackerAPI/app/.venv/bin/python", "/srv/WalletTrackerAPI/app/migrate_all.py"]
  restart_on_secret_changes = "never"
  restart_stop_signal = "SIGTERM"
}
