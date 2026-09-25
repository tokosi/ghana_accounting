# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""Custom fields for the Expense Claim changes."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Expense Claim": [
		{
			"fieldname": "gh_sector_station",
			"fieldtype": "Select",
			"label": "Sector / Station",
			"options": "Head Office\nOperations\nOthers",
			"default": "Head Office",
			"insert_after": "department",
			"reqd": 1,
		},
		{
			"fieldname": "gh_sector_other",
			"fieldtype": "Data",
			"label": "Specify Sector / Station",
			"insert_after": "gh_sector_station",
			"depends_on": "eval:doc.gh_sector_station=='Others'",
			"mandatory_depends_on": "eval:doc.gh_sector_station=='Others'",
		},
		{
			"fieldname": "gh_sector_display",
			"fieldtype": "Data",
			"label": "Sector / Station (resolved)",
			"insert_after": "gh_sector_other",
			"read_only": 1,
			"hidden": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "gh_approval_level",
			"fieldtype": "Data",
			"label": "Approval Level",
			"insert_after": "approval_status",
			"read_only": 1,
			"description": "Set from the claim amount.",
		},
		{
			"fieldname": "gh_board_approval_ref",
			"fieldtype": "Data",
			"label": "Board Approval Reference",
			"insert_after": "gh_approval_level",
			"description": "Board minute or resolution reference. Required when the claim exceeds every approval limit.",
		},
	],
	# Per-row attachment: a receipt belongs to the line it evidences, not to
	# the claim as a whole.
	"Expense Claim Detail": [
		{
			"fieldname": "gh_attachment",
			"fieldtype": "Attach",
			"label": "Receipt",
			"insert_after": "sanctioned_amount",
			"in_list_view": 1,
			"columns": 1,
		},
	],
	"Expense Claim Advance": [
		{
			"fieldname": "gh_attachment",
			"fieldtype": "Attach",
			"label": "Document",
			"insert_after": "allocated_amount",
			"in_list_view": 1,
			"columns": 1,
		},
	],
	# Approval levels live on the accounting settings single.
	"Ghana Accounting Settings": [
		{
			"fieldname": "sec_claim_levels",
			"fieldtype": "Section Break",
			"label": "Claim Approval Thresholds",
			"insert_after": "enable_advance_workflow",
		},
		{
			"fieldname": "claim_levels_html",
			"fieldtype": "HTML",
			"insert_after": "sec_claim_levels",
			"options": "<p class='text-muted small'>The approver is set from the claim amount, overriding whatever the claimant selected. A claim above every limit needs a board reference before it can be submitted.</p>",
		},
		{
			"fieldname": "claim_approval_levels",
			"fieldtype": "Table",
			"label": "Approval Levels",
			"options": "Ghana Claim Approval Level",
			"insert_after": "claim_levels_html",
		},
	],
}


def install_fields():
	create_custom_fields(FIELDS, update=True)
	frappe.db.commit()
	return sorted(FIELDS.keys())


@frappe.whitelist()
def seed_default_levels():
	"""Finance Head 5,000 and Chief Executive 200,000, as a starting point."""
	doc = frappe.get_doc("Ghana Accounting Settings")
	if doc.get("claim_approval_levels"):
		return {"skipped": "levels already configured"}

	for level in (
		{"level_name": "Finance Head", "max_amount": 5000, "approver_role": "Expense Approver"},
		{"level_name": "Chief Executive", "max_amount": 200000, "approver_role": "Expense Approver"},
	):
		doc.append("claim_approval_levels", level)

	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"levels": len(doc.claim_approval_levels)}
