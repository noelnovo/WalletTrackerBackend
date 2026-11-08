"""Read-only contract plan. The historical root-mount writer is retired.

The target for WalletTracker dev records is downops/apps/wallettracker/dev.
Live Vault migration is coordinated by the authorized DownOps operator, with
unchanged-value verification, reader cutover and delayed source retirement.
This utility never acquires credentials, creates engines or writes records/ACLs.
"""
import argparse
import json
from devops.vault.vault_contract import contract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Retired; always refused')
    parser.add_argument('--credentials-file', help='Legacy option; never read')
    args = parser.parse_args()
    if args.apply:
        raise RuntimeError('Legacy Vault bootstrap writes are retired; use authorized operator access with the scoped Vault contract')
    desired = contract(canonical_dev=True)
    print(json.dumps({'mode': 'plan-only', 'operator_access_required': True,
                      'recovery_performed': False, 'vault_writes_supported': False,
                      'canonical_kv_mount': desired['canonical_kv_mount'],
                      'canonical_app_prefix': desired['canonical_app_prefix'],
                      'policies': list(desired['policies']), 'roles': list(desired['roles']),
                      'input_record_keys': desired['required_input_records'],
                      'legacy_shared_records_preserved': desired['legacy_shared_records_preserved']}))


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as error:
        print(json.dumps({'success': False, 'safe_error': str(error)}))
        raise SystemExit(1)
