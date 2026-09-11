# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""Custom fields for the JV / PV rules. Idempotent."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = {
	"Journal Entry": [
		{
			"fieldname": "gh_voucher_class",
			"fieldtype": "Select",
			"label": "Voucher Class",
			"options": "\nJournal Voucher\nPayment Voucher",
			"insert_after": "voucher_type",
			"description": "Drives the voucher number. Set from the voucher type when left blank.",
		},
		{
			"fieldname": "gh_bank_code",
			"fieldtype": "Data",
			"label": "Bank Code",
			"insert_after": "gh_voucher_class",
			"depends_on": "eval:doc.gh_voucher_class=='Payment Voucher'",
			"description": "Short code used in the PV number, e.g. UMB. Derived from the credited bank account when blank.",
		},
	],
	"Journal Entry Account": [
		{
			"fieldname": "gh_line_reference",
			"fieldtype": "Data",
			"label": "Reference",
			"insert_after": "account",
			"reqd": 1,
			"in_list_view": 1,
			"columns": 2,
			"description": "Free-text reference for this line: invoice number, cheque number, contract, etc.",
		},
	],
}


def install_voucher_fields():
	create_custom_fields(FIELDS, update=True)
	frappe.db.commit()
	return sorted(FIELDS.keys())


@frappe.whitelist()
def setup_all():
	"""Fields plus property setters, in one call."""
	from ghana_accounting.voucher_rules import apply_property_setters

	created = install_voucher_fields()
	apply_property_setters()
	return {"custom_fields": created, "property_setters": "applied"}
