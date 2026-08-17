# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""
Workspace Sidebar population for Frappe v16.

v16 introduced a Workspace Sidebar layer between the Workspace and what the
desk actually renders. Creating a Workspace alone is no longer enough: the
sidebar record exists but draws from its own `items` child table, so an empty
table means an empty sidebar even though the workspace is reachable by search.

Field values for `type` and `link_type` are read from the DocType meta at
runtime rather than hardcoded, because those Select options have changed
between versions and a wrong literal fails silently.
"""

import frappe
from frappe.utils import cint

SIDEBAR = "Workspace Sidebar"
SIDEBAR_ITEM = "Workspace Sidebar Item"
NAME = "Ghana Accounting"
APP = "ghana_accounting"
MODULE = "Ghana Accounting"


def _options(doctype, fieldname):
	"""Select options for a field, as a list."""
	try:
		field = frappe.get_meta(doctype).get_field(fieldname)
		if not field or not field.options:
			return []
		return [o.strip() for o in field.options.split("\n") if o.strip()]
	except Exception:
		return []


def _pick(options, *preferred):
	"""First preferred value that the installed version actually offers."""
	for candidate in preferred:
		for option in options:
			if option.lower() == candidate.lower():
				return option
	return options[0] if options else None


def _sample_existing_items():
	"""
	Field values from a working standard sidebar.

	Mirroring what ERPNext itself writes is more reliable than inferring the
	right literals, since these Select options move between versions.
	"""
	for source in ("Payroll", "Stock", "Buying", "Home"):
		if not frappe.db.exists(SIDEBAR, source):
			continue
		try:
			doc = frappe.get_doc(SIDEBAR, source)
			for row in doc.get("items") or []:
				if row.get("link_to"):
					return {
						"type": row.get("type"),
						"link_type": row.get("link_type"),
					}
		except Exception:
			continue
	return {}


def get_items_spec():
	"""What the Ghana Accounting sidebar should contain."""
	return [
		{"label": "Configuration", "group": True},
		{"label": "Ghana Accounting Settings", "doctype": "DocType", "target": "Ghana Accounting Settings"},
		{"label": "Tax Withholding Category", "doctype": "DocType", "target": "Tax Withholding Category"},
		{"label": "Sales Taxes and Charges Template", "doctype": "DocType", "target": "Sales Taxes and Charges Template"},
		{"label": "Purchase Taxes and Charges Template", "doctype": "DocType", "target": "Purchase Taxes and Charges Template"},
		{"label": "Approvals", "group": True},
		{"label": "Expense Claim", "doctype": "DocType", "target": "Expense Claim"},
		{"label": "Employee Advance", "doctype": "DocType", "target": "Employee Advance"},
		{"label": "Journal Entry", "doctype": "DocType", "target": "Journal Entry"},
		{"label": "Compliance Reports", "group": True},
		{"label": "Ghana VAT Return Summary", "doctype": "Report", "target": "Ghana VAT Return Summary"},
		{"label": "Ghana Withholding Tax Schedule", "doctype": "Report", "target": "Ghana Withholding Tax Schedule"},
		{"label": "Ghana Statutory Compliance Summary", "doctype": "Report", "target": "Ghana Statutory Compliance Summary"},
	]


@frappe.whitelist()
def build_sidebar():
	"""Create or repopulate the Ghana Accounting workspace sidebar."""
	if not frappe.db.exists("DocType", SIDEBAR):
		return {"skipped": "Workspace Sidebar doctype not present (pre-v16)"}

	is_new = not frappe.db.exists(SIDEBAR, NAME)
	if is_new:
		doc = frappe.new_doc(SIDEBAR)
		doc.name = NAME
	else:
		doc = frappe.get_doc(SIDEBAR, NAME)

	meta = frappe.get_meta(SIDEBAR)
	if meta.has_field("title"):
		doc.title = NAME
	if meta.has_field("app"):
		doc.app = APP
	if meta.has_field("module"):
		doc.module = MODULE
	if meta.has_field("standard"):
		doc.standard = 1
	if meta.has_field("header_icon"):
		doc.header_icon = "accounting"

	# resolve the right Select literals for this version
	type_opts = _options(SIDEBAR_ITEM, "type")
	link_type_opts = _options(SIDEBAR_ITEM, "link_type")
	sample = _sample_existing_items()

	link_type_value = sample.get("type") or _pick(type_opts, "Link", "Item")
	group_type_value = _pick(type_opts, "Group", "Section", "Card Break", "Spacer") or link_type_value

	item_meta = frappe.get_meta(SIDEBAR_ITEM)
	doc.set("items", [])

	for spec in get_items_spec():
		if spec.get("group"):
			row = doc.append("items", {})
			row.label = spec["label"]
			if item_meta.has_field("type"):
				row.type = group_type_value
			if item_meta.has_field("collapsible"):
				row.collapsible = 1
			continue

		target_doctype = spec["doctype"]
		if not frappe.db.exists(target_doctype, spec["target"]):
			# a sidebar item pointing at a missing target renders as a dead link
			continue

		row = doc.append("items", {})
		row.label = spec["label"]
		if item_meta.has_field("type"):
			row.type = link_type_value
		if item_meta.has_field("link_type"):
			row.link_type = _pick(link_type_opts, target_doctype) or target_doctype
		if item_meta.has_field("link_to"):
			row.link_to = spec["target"]
		if item_meta.has_field("indent"):
			row.indent = 1

	doc.flags.ignore_permissions = True
	if is_new:
		doc.insert(ignore_permissions=True)
	else:
		doc.save(ignore_permissions=True)

	frappe.db.commit()
	frappe.clear_cache()

	return {
		"sidebar": doc.name,
		"items": len(doc.get("items") or []),
		"type_used": link_type_value,
		"group_type_used": group_type_value,
		"link_type_options": link_type_opts,
		"type_options": type_opts,
	}


@frappe.whitelist()
def inspect_sidebar(name=None):
	"""Dump a sidebar's items — for comparing against a working one."""
	name = name or NAME
	if not frappe.db.exists(SIDEBAR, name):
		return {"error": "{0} not found".format(name)}
	doc = frappe.get_doc(SIDEBAR, name)
	return {
		"name": doc.name,
		"app": doc.get("app"),
		"module": doc.get("module"),
		"standard": cint(doc.get("standard")),
		"items": [
			{
				"label": r.get("label"),
				"type": r.get("type"),
				"link_type": r.get("link_type"),
				"link_to": r.get("link_to"),
			}
			for r in (doc.get("items") or [])
		],
	}
