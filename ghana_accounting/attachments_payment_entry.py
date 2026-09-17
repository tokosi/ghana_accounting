# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""
Supporting documents on Payment Entry.

Reuses the Ghana Claim Document child table already on Expense Claim, so a
receipt looks the same whether it arrived with a staff claim or a supplier
payment, and the same approver habits apply to both.
"""

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint

FIELDS = {
	"Payment Entry": [
		{
			"fieldname": "gh_docs_section",
			"fieldtype": "Section Break",
			"label": "Supporting Documents",
			"insert_after": "reference_date",
			"collapsible": 1,
		},
		{
			"fieldname": "gh_documents",
			"fieldtype": "Table",
			"label": "Documents",
			"options": "Ghana Claim Document",
			"insert_after": "gh_docs_section",
			"description": "Invoice, receipt or proof of delivery supporting this payment.",
		},
		{
			"fieldname": "gh_has_attachments",
			"fieldtype": "Check",
			"label": "Has Supporting Documents",
			"insert_after": "gh_documents",
			"read_only": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "gh_attachment_count",
			"fieldtype": "Int",
			"label": "Document Count",
			"insert_after": "gh_has_attachments",
			"read_only": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "gh_attachment_summary",
			"fieldtype": "Small Text",
			"label": "Document Summary",
			"insert_after": "gh_attachment_count",
			"read_only": 1,
			"print_hide": 1,
		},
	],
	"Journal Entry": [
		{
			"fieldname": "gh_je_docs_section",
			"fieldtype": "Section Break",
			"label": "Supporting Documents",
			"insert_after": "user_remark",
			"collapsible": 1,
		},
		{
			"fieldname": "gh_documents",
			"fieldtype": "Table",
			"label": "Documents",
			"options": "Ghana Claim Document",
			"insert_after": "gh_je_docs_section",
		},
		{
			"fieldname": "gh_has_attachments",
			"fieldtype": "Check",
			"label": "Has Supporting Documents",
			"insert_after": "gh_documents",
			"read_only": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "gh_attachment_count",
			"fieldtype": "Int",
			"label": "Document Count",
			"insert_after": "gh_has_attachments",
			"read_only": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "gh_attachment_summary",
			"fieldtype": "Small Text",
			"label": "Document Summary",
			"insert_after": "gh_attachment_count",
			"read_only": 1,
			"print_hide": 1,
		},
	],
}


def validate_documents(doc, method=None):
	"""
	Shared validate hook.

	Deliberately generic: it reads `gh_documents` and writes the summary
	fields, so the same function serves Expense Claim, Payment Entry and
	Journal Entry rather than three near-identical copies.
	"""
	rows = doc.get("gh_documents") or []

	for row in rows:
		if not row.attachment:
			frappe.throw(
				_("Row {0} in Supporting Documents has no file attached.").format(row.idx)
			)

	native = []
	if doc.get("name") and not doc.get("__islocal"):
		try:
			native = frappe.get_all(
				"File",
				filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
				fields=["file_name"],
			)
		except Exception:
			native = []

	labels = []
	for row in rows:
		label = row.document_type or _("Document")
		if row.reference:
			label = "{0} {1}".format(label, row.reference)
		labels.append(label)

	if native:
		labels.append(_("{0} file(s) attached to the record").format(len(native)))

	doc.gh_has_attachments = 1 if (rows or native) else 0
	doc.gh_attachment_count = len(rows) + len(native)
	doc.gh_attachment_summary = "; ".join(labels) if labels else ""


@frappe.whitelist()
def install_document_fields():
	"""Add the table to Payment Entry and Journal Entry. Safe to re-run."""
	if not frappe.db.exists("DocType", "Ghana Claim Document"):
		frappe.throw(
			_("The Ghana Claim Document doctype is missing. Deploy the claim documents package first.")
		)

	create_custom_fields(FIELDS, update=True)
	frappe.db.commit()
	return {"doctypes": sorted(FIELDS.keys())}
