"""Terraform external data adapter. Credentials arrive over stdin, not argv."""
import json
import sys
import urllib.request


def main():
    query = json.load(sys.stdin)
    request = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/" + query["account_id"] + "/cfd_tunnel?is_deleted=false&per_page=1000",
        headers={"Authorization": "Bearer " + query["token"]},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    if not data.get("success"):
        raise RuntimeError()
    matches = [item for item in data["result"] if item.get("name") == "wallettracker-api" and not item.get("deleted_at")]
    # Existing production connector identity is owned by its Agent bootstrap.
    # Missing/ambiguous tunnels are not permission to create a replacement.
    if len(matches) != 1:
        raise RuntimeError()
    print(json.dumps({"exists": "true", "tunnel_id": matches[0]["id"]}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Existing WalletTracker tunnel lookup failed; diagnostics suppressed", file=sys.stderr)
        sys.exit(1)
