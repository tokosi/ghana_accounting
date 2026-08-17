# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""
Workspace dashboard: number cards and shortcuts.

Cards aggregate GL Entry rather than source documents, so they report what was
actually posted to the ledger rather than what a document intended to post.

Payroll obligations (PAYE, SSNIT, Provident Fund) are included only when the
matching ledger accounts exist, which keeps this app standalone.
"""

import frappe
from frappe.utils import cint

APP = "ghana_accounting"

# (card name, label, account name, colour, belongs to payroll)
CARDS = [
	("Ghana VAT Output Payable", "VAT Output Payable", "VAT Output Payable", "#984A35", False),
	("Ghana WHT Payable", "WHT Payable", "WHT Payable - Suppliers", "#C89A12", False),
	("Ghana NHIL Payable", "NHIL Payable", "NHIL Output Payable", "#C3705A", False),
	("Ghana GETFund Payable", "GETFund Payable", "GETFund Output Payable", "#DDA08B", False),
	("Ghana PAYE Payable", "PAYE Payable", "PAYE Payable", "#6B3222", True),
	("Ghana SSNIT Payable", "SSNIT Payable", "SSNIT Payable", "#17803A", True),
]

SHORTCUTS = [
	{"label": "Ghana Accounting Settings", "type": "DocType", "link_to": "Ghana Accounting Settings"},
	{"label": "Expense Claim", "type": "DocType", "link_to": "Expense Claim"},
	{"label": "Employee Advance", "type": "DocType", "link_to": "Employee Advance"},
	{"label": "Journal Entry", "type": "DocType", "link_to": "Journal Entry"},
]

REPORTS = [
	"Ghana VAT Return Summary",
	"Ghana Withholding Tax Schedule",
	"Ghana Statutory Compliance Summary",
]


def _block(block_type, data):
	return {"id": frappe.generate_hash(length=8), "type": block_type, "data": data}


def create_number_cards():
	"""One outstanding-balance card per statutory account that exists."""
	if not frappe.db.exists("DocType", "Number Card"):
		return []

	created = []
	for name, label, account_name, colour, _is_payroll in CARDS:
		if frappe.db.exists("Number Card", name):
			continue

		accounts = frappe.get_all("Account", filters={"account_name": account_name}, pluck="name")
		if not accounts:
			# A card pointing at a missing account raises on every workspace
			# load, so it is skipped until the account is created.
			continue

		try:
			card = frappe.new_doc("Number Card")
			card.name = name
			card.label = label
			card.type = "Document Type"
			card.document_type = "GL Entry"
			card.function = "Sum"
			card.aggregate_function_based_on = "credit"
			card.filters_json = frappe.as_json(
				[
					["GL Entry", "account", "in", accounts],
					["GL Entry", "is_cancelled", "=", 0],
				]
			)
			card.is_public = 1
			card.show_percentage_stats = 1
			card.stats_time_interval = "Monthly"
			if card.meta.has_field("color"):
				card.color = colour
			if card.meta.has_field("module"):
				card.module = "Ghana Accounting"
			card.flags.ignore_permissions = True
			card.insert(ignore_permissions=True)
			created.append(name)
		except Exception:
			frappe.log_error(
				title="Ghana Accounting: number card {0}".format(name),
				message=frappe.get_traceback(),
			)

	return created


def build_workspace():
	"""Create or rebuild the Ghana Accounting workspace."""
	name = "Ghana Accounting"
	is_new = not frappe.db.exists("Workspace", name)

	if is_new:
		ws = frappe.new_doc("Workspace")
		ws.name = name
		ws.title = name
	else:
		ws = frappe.get_doc("Workspace", name)

	ws.label = name
	ws.public = 1
	ws.is_hidden = 0
	# v16 scopes the desk sidebar by app; without this the workspace exists but
	# cannot be reached from the app switcher.
	if ws.meta.has_field("app"):
		ws.app = APP
	if ws.meta.has_field("icon"):
		ws.icon = "accounting"
	if ws.meta.has_field("module"):
		ws.module = "Ghana Accounting"

	# ---- links ----
	ws.links = []
	link_spec = [
		("Card Break", "Configuration", None, None, 0),
		("Link", "Ghana Accounting Settings", "DocType", "Ghana Accounting Settings", 0),
		("Link", "Tax Withholding Category", "DocType", "Tax Withholding Category", 0),
		("Link", "Sales Taxes and Charges Template", "DocType", "Sales Taxes and Charges Template", 0),
		("Link", "Purchase Taxes and Charges Template", "DocType", "Purchase Taxes and Charges Template", 0),
		("Card Break", "Approvals", None, None, 0),
		("Link", "Expense Claim", "DocType", "Expense Claim", 0),
		("Link", "Employee Advance", "DocType", "Employee Advance", 0),
		("Link", "Journal Entry", "DocType", "Journal Entry", 0),
		("Link", "Workflow", "DocType", "Workflow", 0),
		("Card Break", "Compliance Reports", None, None, 0),
	] + [("Link", r, "Report", r, 1) for r in REPORTS]

	for link_type, label, kind, target, is_query in link_spec:
		if link_type == "Link":
			doctype = "Report" if is_query else kind
			if not frappe.db.exists(doctype, target):
				continue
		row = ws.append("links", {})
		row.type = link_type
		row.label = label
		row.hidden = 0
		row.onboard = 0
		if link_type == "Link":
			row.link_type = "Report" if is_query else kind
			row.link_to = target
			if is_query:
				row.is_query_report = 1

	# ---- cards ----
	cards = [c[0] for c in CARDS if frappe.db.exists("Number Card", c[0])]
	if ws.meta.has_field("number_cards"):
		ws.number_cards = []
		for card_name in cards:
			row = ws.append("number_cards", {})
			row.number_card_name = card_name
			row.label = frappe.db.get_value("Number Card", card_name, "label")

	# ---- shortcuts ----
	if ws.meta.has_field("shortcuts"):
		ws.shortcuts = []
		for spec in SHORTCUTS:
			if not frappe.db.exists("DocType", spec["link_to"]):
				continue
			row = ws.append("shortcuts", {})
			row.label = spec["label"]
			row.type = spec["type"]
			row.link_to = spec["link_to"]

	# ---- rendered content ----
	content = []
	if cards:
		content.append(_block("header", {"text": "Statutory Position", "col": 12}))
		for card_name in cards[:4]:
			content.append(_block("number_card", {"number_card_name": card_name, "col": 3}))

	if ws.shortcuts:
		content.append(_block("header", {"text": "Shortcuts", "col": 12}))
		for s in ws.shortcuts:
			content.append(_block("shortcut", {"shortcut_name": s.label, "col": 3}))

	content.append(_block("header", {"text": "Configuration & Reports", "col": 12}))
	for card_name in ("Configuration", "Approvals", "Compliance Reports"):
		content.append(_block("card", {"card_name": card_name, "col": 4}))

	ws.content = frappe.as_json(content)
	ws.flags.ignore_permissions = True

	if is_new:
		ws.insert(ignore_permissions=True)
	else:
		ws.save(ignore_permissions=True)

	return ws.name


@frappe.whitelist()
def build_dashboards():
	"""Create cards and rebuild the workspace. Safe to re-run."""
	result = {"cards": [], "workspace": None, "errors": []}

	try:
		result["cards"] = create_number_cards()
	except Exception as e:
		result["errors"].append("cards: {0}".format(e))
		frappe.log_error(title="Ghana Accounting: cards", message=frappe.get_traceback())

	try:
		result["workspace"] = build_workspace()
	except Exception as e:
		result["errors"].append("workspace: {0}".format(e))
		frappe.log_error(title="Ghana Accounting: workspace", message=frappe.get_traceback())

	frappe.db.commit()
	frappe.clear_cache()
	return result
