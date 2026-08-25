# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""
Registers the Ghana Payment Voucher and Journal Voucher print formats.

Drop-in: works whether or not the HTML lives inside an app. Run from the
console:

    from ghana_accounting.voucher_formats import install_vouchers
    print(install_vouchers())

or, if you copied this file somewhere loose:

    bench --site <site> execute path.to.voucher_formats.install_vouchers
"""

import os

import frappe

# (print format name, template file, doctype)
FORMATS = [
	("Ghana Payment Voucher", "ghana_payment_voucher.html", "Journal Entry"),
	("Ghana Journal Voucher", "ghana_journal_voucher.html", "Journal Entry"),
	("Ghana Payment Voucher (Payment Entry)", "ghana_payment_voucher_pe.html", "Payment Entry"),
]

# Fields the Topaz voucher carries that ERPNext's Journal Entry has no
# equivalent for. Without these the template falls back to bill_no and 0.00,
# which is correct but loses the batch reference.
CUSTOM_FIELDS = {
	"Journal Entry": [
		{
			"fieldname": "gh_voucher_section",
			"fieldtype": "Section Break",
			"label": "Voucher Details",
			"insert_after": "cheque_date",
			"collapsible": 1,
		},
		{
			"fieldname": "gh_batch_no",
			"fieldtype": "Data",
			"label": "Batch No.",
			"insert_after": "gh_voucher_section",
		},
		{
			"fieldname": "gh_voucher_cb",
			"fieldtype": "Column Break",
			"insert_after": "gh_batch_no",
		},
		{
			"fieldname": "gh_withholding_rate",
			"fieldtype": "Percent",
			"label": "Withholding Rate",
			"insert_after": "gh_voucher_cb",
			"default": "0",
		},
	]
}


def _template_dir():
	"""Where the HTML lives: inside the app if installed, else beside this file."""
	try:
		app_path = os.path.join(
			frappe.get_app_path("ghana_accounting"), "templates", "print_formats"
		)
		if os.path.isdir(app_path):
			return app_path
	except Exception:
		pass
	return os.path.dirname(os.path.abspath(__file__))


def create_custom_fields_for_vouchers():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(CUSTOM_FIELDS, update=True)


@frappe.whitelist()
def install_vouchers():
	"""Create or update both print formats. Safe to re-run."""
	result = {"created": [], "updated": [], "missing": [], "errors": []}

	try:
		create_custom_fields_for_vouchers()
	except Exception as e:
		result["errors"].append("custom fields: {0}".format(e))
		frappe.log_error(title="Voucher formats: custom fields", message=frappe.get_traceback())

	directory = _template_dir()

	for name, filename, doctype in FORMATS:
		path = os.path.join(directory, filename)
		if not os.path.exists(path):
			result["missing"].append(path)
			continue

		try:
			with open(path, "r", encoding="utf-8") as fh:
				html = fh.read()

			is_new = not frappe.db.exists("Print Format", name)
			doc = frappe.new_doc("Print Format") if is_new else frappe.get_doc("Print Format", name)

			doc.name = name
			doc.doc_type = doctype
			doc.standard = "No"
			doc.custom_format = 1
			doc.print_format_type = "Jinja"
			doc.html = html

			if doc.meta.has_field("module"):
				doc.module = "Ghana Accounting" if frappe.db.exists(
					"Module Def", "Ghana Accounting"
				) else None

			# The template sets its own @page margins, so the wrapper margins
			# are kept small to avoid doubling them.
			for field, value in (
				("margin_top", 10),
				("margin_bottom", 10),
				("margin_left", 8),
				("margin_right", 8),
			):
				if doc.meta.has_field(field):
					doc.set(field, value)

			# Only set on creation: an administrator may have disabled one
			# deliberately, and a migrate should not silently re-enable it.
			if is_new and doc.meta.has_field("disabled"):
				doc.disabled = 0

			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)

			(result["created"] if is_new else result["updated"]).append(name)
		except Exception as e:
			result["errors"].append("{0}: {1}".format(name, e))
			frappe.log_error(
				title="Voucher formats: {0}".format(name), message=frappe.get_traceback()
			)

	frappe.db.commit()
	frappe.clear_cache()
	return result


@frappe.whitelist()
def set_default(print_format="Ghana Payment Voucher", doctype="Journal Entry"):
	"""Make one of them the default layout for its doctype."""
	if not frappe.db.exists("Print Format", print_format):
		return {"error": "{0} not found".format(print_format)}

	settings = frappe.get_doc("Property Setter", {"doc_type": doctype, "property": "default_print_format"}) \
		if frappe.db.exists(
			"Property Setter", {"doc_type": doctype, "property": "default_print_format"}
		) else None

	if settings:
		settings.value = print_format
		settings.flags.ignore_permissions = True
		settings.save(ignore_permissions=True)
	else:
		frappe.make_property_setter(
			{
				"doctype": doctype,
				"doctype_or_field": "DocType",
				"property": "default_print_format",
				"value": print_format,
				"property_type": "Data",
			},
			ignore_validate=True,
		)

	frappe.db.commit()
	return {"default_print_format": print_format}
