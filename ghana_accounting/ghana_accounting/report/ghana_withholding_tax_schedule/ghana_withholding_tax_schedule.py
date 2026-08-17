# Copyright (c) 2026, Ghana Payroll Contributors
# License: MIT

"""
Ghana Withholding Tax Schedule.

One row per withheld payment, in the shape needed for the monthly WHT return
and for issuing suppliers their withholding certificates. Reads the GL against
the WHT payable account, so it picks up whatever ERPNext's Tax Withholding
Category engine actually posted rather than re-deriving the deduction.
"""

import frappe
from frappe import _
from frappe.utils import flt

WHT_ACCOUNT_NAME = "WHT Payable - Suppliers"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.from_date or not filters.to_date:
		frappe.throw(_("Company and date range are required."))

	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data)


def get_columns():
	return [
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 100},
		{"label": _("Voucher Type"), "fieldname": "voucher_type", "fieldtype": "Data", "width": 130},
		{"label": _("Voucher"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
		{"label": _("Supplier"), "fieldname": "party", "fieldtype": "Link", "options": "Supplier", "width": 180},
		{"label": _("Supplier TIN"), "fieldname": "tax_id", "fieldtype": "Data", "width": 130},
		{"label": _("WHT Category"), "fieldname": "category", "fieldtype": "Data", "width": 220},
		{"label": _("Rate"), "fieldname": "rate", "fieldtype": "Percent", "width": 80},
		{"label": _("Tax Withheld"), "fieldname": "amount", "fieldtype": "Currency", "width": 150},
	]


def get_data(filters):
	accounts = frappe.get_all(
		"Account", filters={"company": filters.company, "account_name": WHT_ACCOUNT_NAME}, pluck="name"
	)
	if not accounts:
		frappe.msgprint(
			_("No account named {0} exists for this company. Run the Ghana accounting setup first.").format(
				frappe.bold(WHT_ACCOUNT_NAME)
			)
		)
		return []

	rows = frappe.db.sql(
		"""
		SELECT gle.posting_date, gle.voucher_type, gle.voucher_no,
		       gle.against AS party, gle.credit - gle.debit AS amount
		FROM `tabGL Entry` gle
		WHERE gle.company = %(company)s
		  AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND gle.is_cancelled = 0
		  AND gle.account IN %(accounts)s
		ORDER BY gle.posting_date, gle.voucher_no
		""",
		{
			"company": filters.company,
			"from_date": filters.from_date,
			"to_date": filters.to_date,
			"accounts": tuple(accounts),
		},
		as_dict=True,
	)

	for row in rows:
		row["amount"] = flt(row.get("amount"), 2)
		supplier = _supplier_for(row)
		row["party"] = supplier
		row["tax_id"] = frappe.db.get_value("Supplier", supplier, "tax_id") if supplier else None
		row["category"] = (
			frappe.db.get_value("Supplier", supplier, "tax_withholding_category") if supplier else None
		)
		row["rate"] = _rate_for(row["category"])

	return [r for r in rows if r["amount"]]


def _supplier_for(row):
	"""GL 'against' can hold accounts rather than the party; fall back to the voucher."""
	for doctype, field in (("Purchase Invoice", "supplier"), ("Payment Entry", "party")):
		if row.get("voucher_type") == doctype:
			return frappe.db.get_value(doctype, row.get("voucher_no"), field)
	return row.get("party")


def _rate_for(category):
	if not category:
		return 0
	rate = frappe.db.get_value(
		"Tax Withholding Rate", {"parent": category}, "tax_withholding_rate", order_by="creation desc"
	)
	return flt(rate)


def get_summary(data):
	return [
		{"label": _("Payments Withheld"), "value": len(data), "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Total WHT Payable to GRA"),
			"value": sum(r.get("amount") or 0 for r in data),
			"datatype": "Currency",
			"indicator": "Red",
		},
	]
