# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

app_name = "ghana_accounting"
app_title = "Ghana Accounting"
app_publisher = "Ghana Accounting Contributors"
app_description = (
	"Ghana tax compliance for ERPNext: VAT/NHIL/GETFund under Act 1151, withholding tax, "
	"two-level claim and advance approval, and journal voucher maker-checker"
)
app_email = "support@example.com"
app_license = "mit"
app_version = "1.1.0"

# ERPNext only. Payroll integration is optional and detected at runtime, so
# this app installs and runs on a site without the Ghana Payroll app.
required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# App switcher tile
# ---------------------------------------------------------------------------
add_to_apps_screen = [
	{
		"name": "ghana_accounting",
		"logo": "/assets/ghana_accounting/images/ghana_accounting.svg",
		"title": "Ghana Accounting",
		"route": "/app/ghana-accounting",
	},
]

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
after_install = "ghana_accounting.install.after_install"
after_migrate = "ghana_accounting.install.after_migrate"
before_uninstall = "ghana_accounting.install.before_uninstall"

fixtures = []
