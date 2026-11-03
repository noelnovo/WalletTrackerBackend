"""Print only resource actions. Never print raw plans, variables or state values.

The existing production guests/database/tunnel must never be replaced by CD.
Only release-triggered null resources may be replaced. New infrastructure needs
its own explicitly reviewed provisioning workflow, not this maintenance job.
"""
import json
import sys

REPLACEABLE = {"null_resource.deploy_api", "null_resource.deploy_mariadb"}


def check(plan):
    blocked = []
    for change in plan.get("resource_changes", []):
        address = change["address"]
        actions = change["change"]["actions"]
        if actions == ["no-op"]:
            continue
        print(address, ",".join(actions))
        if change.get("mode") == "data":
            continue
        if ("delete" in actions or "create" in actions) and address not in REPLACEABLE:
            blocked.append(address)
    if blocked:
        raise RuntimeError("Unsafe infrastructure creation/replacement/deletion blocked: " + ", ".join(blocked))


if __name__ == "__main__":
    try:
        check(json.load(sys.stdin))
    except Exception as error:
        print(str(error) if isinstance(error, RuntimeError) else "Invalid Terraform plan", file=sys.stderr)
        sys.exit(1)
