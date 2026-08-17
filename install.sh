#!/usr/bin/env bash
# Ghana Accounting installer
set -euo pipefail
SITE="${1:-}"
APP_PATH="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

if [[ -z "$SITE" ]]; then echo "Usage: ./install.sh <site-name> [path]"; exit 1; fi
if [[ ! -f "sites/common_site_config.json" ]]; then
  echo "ERROR: run from your frappe-bench directory."; exit 1
fi
if [[ ! -d "apps/erpnext" ]]; then
  echo "ERROR: erpnext is required. bench get-app erpnext first."; exit 1
fi

[[ -d "apps/ghana_accounting" ]] || bench get-app ghana_accounting "$APP_PATH"
bench --site "$SITE" install-app ghana_accounting
bench --site "$SITE" migrate
bench build --app ghana_accounting
bench --site "$SITE" clear-cache
bench restart || echo "  (bench restart skipped — restart your processes manually)"

cat <<'DONE'

============================================================
 Ghana Accounting installed.

 Next:
   1. Ghana Accounting Settings — confirm levy rates against
      the current GRA schedule.
   2. Setup > Run Accounting Setup.
   3. Assign the four Ghana approver roles to users.
   4. Leave the Journal Voucher workflow OFF until you have
      run a test payroll entry with it enabled.
============================================================
DONE
