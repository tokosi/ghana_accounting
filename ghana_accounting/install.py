# Copyright (c) 2026, Ghana Payroll Contributors
# License: MIT

"""
Ghana Accounting setup.

This app is standalone. Where a figure belongs to payroll (PAYE, SSNIT,
Provident Fund) the compliance report reads the ledger account by name and
simply omits the line when the account is absent, so the app installs and runs
correctly whether or not the Ghana Payroll app is present.

Covers GRA indirect tax (VAT 15% + NHIL 2.5% + GETFund 2.5% on a common base
under Act 1151, effective 1 January 2026), withholding tax, and the approval
workflows for claims, advances and journal vouchers.

Everything here is idempotent and safe to re-run on migrate.
"""

import os

import frappe
from frappe.utils import cint, flt

# ----------------------------------------------------------------------
# GRA indirect tax structure (Act 1151, from 1 Jan 2026)
# ----------------------------------------------------------------------
# All three are charged on the same taxable value, giving 20% combined.
# The 1% COVID-19 Health Recovery Levy was repealed. NHIL and GETFund were
# re-coupled to the VAT base and are once again recoverable as input tax,
# which is why each has both an output and an input account below.
LEVY_STRUCTURE = [
	{"key": "nhil", "label": "NHIL", "rate": 2.5},
	{"key": "getfund", "label": "GETFund Levy", "rate": 2.5},
	{"key": "vat", "label": "VAT", "rate": 15.0},
]

TAX_ACCOUNTS = [
	("VAT Output Payable", "Liability", "Tax"),
	("NHIL Output Payable", "Liability", "Tax"),
	("GETFund Output Payable", "Liability", "Tax"),
	("WHT Payable - Suppliers", "Liability", "Tax"),
	("VAT Input Recoverable", "Asset", "Tax"),
	("NHIL Input Recoverable", "Asset", "Tax"),
	("GETFund Input Recoverable", "Asset", "Tax"),
]

# Common resident WHT rates. Seeded as ERPNext Tax Withholding Categories so
# the native engine does the deduction. Verify against the current GRA table
# before relying on any of these.
WHT_CATEGORIES = [
	{"name": "Ghana WHT - Goods (Resident) 3%", "rate": 3.0, "threshold": 2000},
	{"name": "Ghana WHT - Works (Resident) 5%", "rate": 5.0, "threshold": 2000},
	{"name": "Ghana WHT - Services (Resident) 7.5%", "rate": 7.5, "threshold": 2000},
	{"name": "Ghana WHT - Rent Residential 8%", "rate": 8.0, "threshold": 0},
	{"name": "Ghana WHT - Rent Commercial 15%", "rate": 15.0, "threshold": 0},
	{"name": "Ghana WHT - Dividend 8%", "rate": 8.0, "threshold": 0},
	{"name": "Ghana WHT - Director Fees 20%", "rate": 20.0, "threshold": 0},
	{"name": "Ghana WHT - Commission to Agents 10%", "rate": 10.0, "threshold": 0},
	{"name": "Ghana WHT - Non-Resident Services 20%", "rate": 20.0, "threshold": 0},
]

GHANA_ROLES = [
	"Ghana Claim Approver L1",
	"Ghana Claim Approver L2",
	"Ghana JV Inputter",
	"Ghana JV Authorizer",
]


# ======================================================================
# entry point
# ======================================================================
def seed_accounting_settings():
	"""Populate the settings single with the statutory levy structure."""
	if not frappe.db.exists("DocType", "Ghana Accounting Settings"):
		return None
	try:
		doc = frappe.get_doc("Ghana Accounting Settings")
		if not doc.levy_rates:
			from ghana_accounting.ghana_accounting.doctype.ghana_accounting_settings.ghana_accounting_settings import (
				DEFAULT_LEVIES,
			)

			for levy in DEFAULT_LEVIES:
				doc.append("levy_rates", levy)
		doc.flags.ignore_permissions = True
		doc.flags.ignore_mandatory = True
		doc.save(ignore_permissions=True)
		return doc
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: settings seed skipped", message=frappe.get_traceback()
		)
		return None


def get_accounting_settings():
	try:
		return frappe.get_cached_doc("Ghana Accounting Settings")
	except Exception:
		return None


def setup_accounting():
	summary = {"companies": [], "roles": len(GHANA_ROLES), "skipped": None}

	create_roles()
	seed_accounting_settings()

	companies = ghana_companies()
	if not companies:
		summary["skipped"] = (
			"No company found. Set country = Ghana on the company (or set a default "
			"company), then re-run."
		)

	for company in companies:
		create_tax_accounts(company)
		create_tax_templates(company)
		create_wht_categories(company)
		summary["companies"].append(company)

	create_workflows()
	create_voucher_print_format()
	frappe.db.commit()
	return summary


def ghana_companies():
	"""
	Companies to configure.

	Preference order: companies explicitly marked country = Ghana, then the
	default company, then a lone company if the site only has one. Returning an
	empty list here is why setup can appear to do nothing at all, so the single
	company case is treated as unambiguous rather than skipped.
	"""
	companies = frappe.get_all("Company", filters={"country": "Ghana"}, pluck="name")
	if companies:
		return companies

	default = frappe.defaults.get_user_default("Company") or frappe.db.get_single_value(
		"Global Defaults", "default_company"
	)
	if default:
		return [default]

	all_companies = frappe.get_all("Company", pluck="name")
	if len(all_companies) == 1:
		return all_companies

	frappe.log_error(
		title="Ghana Accounting: no company selected",
		message=(
			"No company has country = Ghana and no default company is set, so tax "
			"accounts, templates and WHT categories were not created. Set the "
			"country on the company, then run "
			"ghana_accounting.install.rerun_accounting_setup()."
		),
	)
	return []


# ======================================================================
# roles
# ======================================================================
def create_roles():
	for role in GHANA_ROLES:
		if frappe.db.exists("Role", role):
			continue
		doc = frappe.new_doc("Role")
		doc.role_name = role
		doc.desk_access = 1
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


# ======================================================================
# chart of accounts
# ======================================================================
def _parent_group(company, root_type):
	preferred = (
		["Duties and Taxes", "Current Liabilities"]
		if root_type == "Liability"
		else ["Tax Assets", "Current Assets", "Loans and Advances (Assets)"]
	)
	for account_name in preferred:
		found = frappe.db.get_value(
			"Account", {"company": company, "account_name": account_name, "is_group": 1}, "name"
		)
		if found:
			return found
	return frappe.db.get_value(
		"Account", {"company": company, "root_type": root_type, "is_group": 1}, "name"
	)


def get_or_create_account(company, account_name, root_type="Liability", account_type="Tax"):
	existing = frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")
	if existing:
		return existing

	parent = _parent_group(company, root_type)
	if not parent:
		return None

	try:
		acc = frappe.new_doc("Account")
		acc.account_name = account_name
		acc.parent_account = parent
		acc.company = company
		acc.root_type = root_type
		acc.report_type = "Balance Sheet"
		acc.is_group = 0
		if account_type:
			acc.account_type = account_type
		acc.flags.ignore_permissions = True
		acc.insert(ignore_permissions=True)
		return acc.name
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: account {0}".format(account_name),
			message=frappe.get_traceback(),
		)
		return None


def create_tax_accounts(company):
	for account_name, root_type, account_type in TAX_ACCOUNTS:
		get_or_create_account(company, account_name, root_type, account_type)


# ======================================================================
# sales / purchase tax templates
# ======================================================================
def _levy_rows(company, direction):
	"""
	Build the charge rows from Ghana Accounting Settings.

	Reading the configured table rather than a constant means an administrator
	can respond to a rate change without a code deployment, which matters
	because these rates move with the budget.
	"""
	settings = get_accounting_settings()
	configured = [r for r in (settings.levy_rates or [])] if settings else []

	if configured:
		rows = []
		for levy in configured:
			if direction == "purchase" and not cint(levy.recoverable):
				continue
			account = levy.input_account if direction == "purchase" else levy.output_account
			if not account:
				suffix = "Input Recoverable" if direction == "purchase" else "Output Payable"
				base = (levy.levy_name or "").replace(" Levy", "")
				account = get_or_create_account(
					company,
					"{0} {1}".format(base, suffix),
					"Asset" if direction == "purchase" else "Liability",
					"Tax",
				)
			if not account:
				continue
			rows.append(
				{
					"charge_type": levy.charge_type or "On Net Total",
					"account_head": account,
					"description": "{0} @ {1}%".format(levy.levy_name, flt(levy.rate)),
					"rate": flt(levy.rate),
				}
			)
		return rows

	return _levy_rows_from_defaults(company, direction)


def _levy_rows_from_defaults(company, direction):
	"""
	Build the three charge rows.

	Each is 'On Net Total' rather than compounding, because Act 1151 charges
	VAT, NHIL and GETFund on the same taxable value. Stacking them would
	reproduce the pre-2026 cascade the reform removed.
	"""
	rows = []
	for levy in LEVY_STRUCTURE:
		if direction == "sales":
			account_name = "{0} Output Payable".format(levy["label"].replace(" Levy", ""))
			root_type = "Liability"
		else:
			account_name = "{0} Input Recoverable".format(levy["label"].replace(" Levy", ""))
			root_type = "Asset"

		account = get_or_create_account(company, account_name, root_type, "Tax")
		if not account:
			continue

		rows.append(
			{
				"charge_type": "On Net Total",
				"account_head": account,
				"description": "{0} @ {1}%".format(levy["label"], levy["rate"]),
				"rate": levy["rate"],
			}
		)
	return rows


def _make_template(doctype, title, company, rows, is_default=0):
	name = "{0} - {1}".format(title, frappe.get_cached_value("Company", company, "abbr"))
	if frappe.db.exists(doctype, name):
		return name

	try:
		doc = frappe.new_doc(doctype)
		doc.title = title
		doc.company = company
		doc.is_default = is_default
		for row in rows:
			doc.append("taxes", row)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: template {0}".format(title), message=frappe.get_traceback()
		)
		return None


def create_tax_templates(company):
	_make_template(
		"Sales Taxes and Charges Template",
		"Ghana VAT Standard 20%",
		company,
		_levy_rows(company, "sales"),
		is_default=1,
	)
	_make_template("Sales Taxes and Charges Template", "Ghana VAT Zero Rated", company, [])
	_make_template("Sales Taxes and Charges Template", "Ghana VAT Exempt", company, [])

	_make_template(
		"Purchase Taxes and Charges Template",
		"Ghana VAT Standard 20% (Input)",
		company,
		_levy_rows(company, "purchase"),
		is_default=1,
	)
	_make_template("Purchase Taxes and Charges Template", "Ghana VAT Exempt (Input)", company, [])


# ======================================================================
# withholding tax
# ======================================================================
def create_wht_categories(company):
	account = get_or_create_account(company, "WHT Payable - Suppliers", "Liability", "Tax")
	if not account:
		return

	fiscal_year = frappe.defaults.get_user_default("fiscal_year") or frappe.db.get_value(
		"Fiscal Year", {}, "name", order_by="year_start_date desc"
	)

	for spec in WHT_CATEGORIES:
		if frappe.db.exists("Tax Withholding Category", spec["name"]):
			continue
		try:
			doc = frappe.new_doc("Tax Withholding Category")
			doc.name = spec["name"]
			doc.category_name = spec["name"]
			rate_row = {"tax_withholding_rate": spec["rate"]}
			if doc.meta.get_field("rates") and frappe.get_meta("Tax Withholding Rate").has_field(
				"from_date"
			):
				rate_row["from_date"] = "2026-01-01"
				rate_row["to_date"] = "2030-12-31"
			elif fiscal_year:
				rate_row["fiscal_year"] = fiscal_year
			if spec["threshold"]:
				rate_row["single_threshold"] = 0
				rate_row["cumulative_threshold"] = spec["threshold"]
			doc.append("rates", rate_row)
			doc.append("accounts", {"company": company, "account": account})
			doc.flags.ignore_permissions = True
			doc.insert(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="Ghana Accounting: WHT category {0}".format(spec["name"]),
				message=frappe.get_traceback(),
			)


# ======================================================================
# workflows
# ======================================================================
def _ensure_workflow_state(state, style="Primary"):
	if not frappe.db.exists("Workflow State", state):
		doc = frappe.new_doc("Workflow State")
		doc.workflow_state_name = state
		doc.style = style
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def _ensure_workflow_action(action):
	if not frappe.db.exists("Workflow Action Master", action):
		doc = frappe.new_doc("Workflow Action Master")
		doc.workflow_action_name = action
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)


def _make_workflow(name, doctype, states, transitions, is_active=1):
	# On re-run, only the active flag is reconciled. Rebuilding states and
	# transitions would discard any customisation an administrator has made.
	if frappe.db.exists("Workflow", name):
		if cint(frappe.db.get_value("Workflow", name, "is_active")) != cint(is_active):
			frappe.db.set_value("Workflow", name, "is_active", cint(is_active))
		return

	for state in states:
		_ensure_workflow_state(state["state"], state.get("style", "Primary"))
	for transition in transitions:
		_ensure_workflow_action(transition["action"])

	try:
		wf = frappe.new_doc("Workflow")
		wf.workflow_name = name
		wf.document_type = doctype
		wf.workflow_state_field = "workflow_state"
		wf.is_active = cint(is_active)
		wf.send_email_alert = 0

		for state in states:
			row = {
				"state": state["state"],
				"doc_status": state["doc_status"],
				"allow_edit": state["allow_edit"],
			}
			if state.get("update_field"):
				row["update_field"] = state["update_field"]
				row["update_value"] = state["update_value"]
			wf.append("states", row)

		for transition in transitions:
			wf.append(
				"transitions",
				{
					"state": transition["state"],
					"action": transition["action"],
					"next_state": transition["next_state"],
					"allowed": transition["allowed"],
					"allow_self_approval": transition.get("allow_self_approval", 0),
				},
			)

		wf.flags.ignore_permissions = True
		wf.insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: workflow {0}".format(name), message=frappe.get_traceback()
		)


def create_workflows():
	"""
	Create the approval workflows the settings enable.

	The Journal Entry workflow is created inactive regardless, because payroll
	posts its accrual journal programmatically. Activation is a deliberate act
	via Ghana Accounting Settings, followed by a test payroll run.
	"""
	settings = get_accounting_settings()

	def wanted(field, default=1):
		if not settings or not settings.meta.has_field(field):
			return bool(default)
		return bool(cint(settings.get(field)))

	# ---- Claim Request (Expense Claim), two levels ----
	_make_workflow(
		"Ghana Claim Request Approval",
		"Expense Claim",
		[
			{"state": "Draft", "doc_status": "0", "allow_edit": "Employee", "style": "Warning"},
			{"state": "Pending Level 1", "doc_status": "0", "allow_edit": "Ghana Claim Approver L1"},
			{"state": "Pending Level 2", "doc_status": "0", "allow_edit": "Ghana Claim Approver L2"},
			{
				"state": "Approved",
				"doc_status": "1",
				"allow_edit": "Expense Approver",
				"style": "Success",
				"update_field": "approval_status",
				"update_value": "Approved",
			},
			{
				"state": "Rejected",
				"doc_status": "0",
				"allow_edit": "Ghana Claim Approver L1",
				"style": "Danger",
				"update_field": "approval_status",
				"update_value": "Rejected",
			},
		],
		[
			{"state": "Draft", "action": "Submit for Approval", "next_state": "Pending Level 1", "allowed": "Employee"},
			{"state": "Pending Level 1", "action": "Approve Level 1", "next_state": "Pending Level 2", "allowed": "Ghana Claim Approver L1"},
			{"state": "Pending Level 1", "action": "Reject", "next_state": "Rejected", "allowed": "Ghana Claim Approver L1"},
			{"state": "Pending Level 2", "action": "Approve Level 2", "next_state": "Approved", "allowed": "Ghana Claim Approver L2"},
			{"state": "Pending Level 2", "action": "Reject", "next_state": "Rejected", "allowed": "Ghana Claim Approver L2"},
		],
		is_active=wanted("enable_claim_workflow"),
	)

	# ---- Cash Advance Request (Employee Advance), two levels ----
	_make_workflow(
		"Ghana Cash Advance Approval",
		"Employee Advance",
		[
			{"state": "Draft", "doc_status": "0", "allow_edit": "Employee", "style": "Warning"},
			{"state": "Pending Level 1", "doc_status": "0", "allow_edit": "Ghana Claim Approver L1"},
			{"state": "Pending Level 2", "doc_status": "0", "allow_edit": "Ghana Claim Approver L2"},
			{
				"state": "Approved",
				"doc_status": "1",
				"allow_edit": "Ghana Claim Approver L2",
				"style": "Success",
				"update_field": "status",
				"update_value": "Unpaid",
			},
			{"state": "Rejected", "doc_status": "0", "allow_edit": "Ghana Claim Approver L1", "style": "Danger"},
		],
		[
			{"state": "Draft", "action": "Submit for Approval", "next_state": "Pending Level 1", "allowed": "Employee"},
			{"state": "Pending Level 1", "action": "Approve Level 1", "next_state": "Pending Level 2", "allowed": "Ghana Claim Approver L1"},
			{"state": "Pending Level 1", "action": "Reject", "next_state": "Rejected", "allowed": "Ghana Claim Approver L1"},
			{"state": "Pending Level 2", "action": "Approve Level 2", "next_state": "Approved", "allowed": "Ghana Claim Approver L2"},
			{"state": "Pending Level 2", "action": "Reject", "next_state": "Rejected", "allowed": "Ghana Claim Approver L2"},
		],
		is_active=wanted("enable_advance_workflow"),
	)

	# ---- Journal Voucher: inputter / authorizer ----
	# Shipped INACTIVE on purpose. Payroll Entry creates and submits its accrual
	# journal entry programmatically; an active workflow on Journal Entry governs
	# docstatus through transitions and will strand or fail that submit. Activate
	# it only after confirming a payroll run still posts cleanly.
	_make_workflow(
		"Ghana Journal Voucher Authorization",
		"Journal Entry",
		[
			{"state": "Draft", "doc_status": "0", "allow_edit": "Ghana JV Inputter", "style": "Warning"},
			{"state": "Pending Authorization", "doc_status": "0", "allow_edit": "Ghana JV Authorizer"},
			{"state": "Posted", "doc_status": "1", "allow_edit": "Ghana JV Authorizer", "style": "Success"},
			{"state": "Returned to Inputter", "doc_status": "0", "allow_edit": "Ghana JV Inputter", "style": "Danger"},
		],
		[
			{
				"state": "Draft",
				"action": "Send for Authorization",
				"next_state": "Pending Authorization",
				"allowed": "Ghana JV Inputter",
			},
			{
				"state": "Pending Authorization",
				"action": "Authorize and Post",
				"next_state": "Posted",
				"allowed": "Ghana JV Authorizer",
				# Segregation of duties: the inputter must not authorise their own voucher.
				"allow_self_approval": 0,
			},
			{
				"state": "Pending Authorization",
				"action": "Return to Inputter",
				"next_state": "Returned to Inputter",
				"allowed": "Ghana JV Authorizer",
			},
			{
				"state": "Returned to Inputter",
				"action": "Resubmit",
				"next_state": "Pending Authorization",
				"allowed": "Ghana JV Inputter",
			},
		],
		is_active=wanted("enable_jv_workflow", default=0),
	)


# ======================================================================
# journal voucher print format
# ======================================================================
def create_voucher_print_format():
	path = os.path.join(
		frappe.get_app_path("ghana_accounting"), "templates", "print_formats", "ghana_journal_voucher.html"
	)
	if not os.path.exists(path):
		return

	with open(path, "r", encoding="utf-8") as f:
		html = f.read()

	name = "Ghana Journal Voucher"
	doc = (
		frappe.get_doc("Print Format", name)
		if frappe.db.exists("Print Format", name)
		else frappe.new_doc("Print Format")
	)
	doc.name = name
	doc.doc_type = "Journal Entry"
	doc.module = "Ghana Accounting"
	doc.standard = "No"
	doc.custom_format = 1
	doc.print_format_type = "Jinja"
	doc.disabled = 0
	doc.html = html
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)


# ======================================================================
# app lifecycle
# ======================================================================
def after_install():
	setup()


def after_migrate():
	setup()


def setup():
	"""Full setup. Idempotent; safe on every migrate."""
	result = setup_accounting()
	try:
		from ghana_accounting.dashboards import build_dashboards

		build_dashboards()
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: dashboards skipped", message=frappe.get_traceback()
		)

	try:
		from ghana_accounting.sidebar import build_sidebar

		build_sidebar()
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: sidebar skipped", message=frappe.get_traceback()
		)

    try:
		from ghana_accounting.voucher_formats import install_vouchers

		install_vouchers()
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: voucher formats skipped", message=frappe.get_traceback()
		)
        
	return result


def before_uninstall():
	"""
	Remove only what this app owns and nothing that holds financial data.

	Accounts, tax templates, withholding categories and any posted transactions
	are deliberately left in place: deleting them would orphan general ledger
	entries and break historical reporting.
	"""
	for doctype, name in (
		("Print Format", "Ghana Journal Voucher"),
		("Workspace", "Ghana Accounting"),
		("Workspace Sidebar", "Ghana Accounting"),
	):
		if frappe.db.exists("DocType", doctype) and frappe.db.exists(doctype, name):
			try:
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			except Exception:
				frappe.log_error(
					title="Ghana Accounting: could not remove {0}".format(name),
					message=frappe.get_traceback(),
				)

	for card in frappe.get_all(
		"Number Card", filters={"name": ("like", "Ghana VAT%")}, pluck="name"
	):
		frappe.delete_doc("Number Card", card, ignore_permissions=True, force=True)


def payroll_app_installed():
	"""Whether the Ghana Payroll app is present on this site."""
	try:
		return "ghana_payroll" in frappe.get_installed_apps()
	except Exception:
		return False


@frappe.whitelist()
def rerun_accounting_setup():
	"""Re-run setup and report what was configured, rather than failing quietly."""
	return setup()
