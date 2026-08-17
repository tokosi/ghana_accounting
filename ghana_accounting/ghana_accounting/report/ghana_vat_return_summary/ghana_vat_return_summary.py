# Copyright (c) 2026, Ghana Payroll Contributors
# License: MIT

"""
Ghana VAT Return Summary.

Lays out the figures needed for the monthly VAT return: output tax on standard,
zero-rated and exempt supplies, recoverable input tax, and the net position.

Under Act 1151 (from 1 January 2026) VAT, NHIL and GETFund are all charged on
the same taxable value and all three are recoverable as input tax, so the report
reads output and input movements straight from the GL against the tax accounts
rather than trying to unpick a levy cascade.
"""

import frappe
from frappe import _
from frappe.utils import flt

OUTPUT_ACCOUNTS = ("VAT Output Payable", "NHIL Output Payable", "GETFund Output Payable")
INPUT_ACCOUNTS = ("VAT Input Recoverable", "NHIL Input Recoverable", "GETFund Input Recoverable")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.from_date or not filters.to_date:
		frappe.throw(_("Company and date range are required."))

	data = get_data(filters)
	return get_columns(), data, None, None, get_summary(data, filters)


def get_columns():
	return [
		{"label": _("Line"), "fieldname": "line", "fieldtype": "Data", "width": 60},
		{"label": _("Description"), "fieldname": "description", "fieldtype": "Data", "width": 320},
		{"label": _("Taxable Value"), "fieldname": "taxable_value", "fieldtype": "Currency", "width": 160},
		{"label": _("Tax"), "fieldname": "tax", "fieldtype": "Currency", "width": 160},
	]


def _account_names(company, account_names):
	return frappe.get_all(
		"Account", filters={"company": company, "account_name": ("in", account_names)}, pluck="name"
	)


def _gl_movement(filters, accounts):
	"""Net credit for output accounts, net debit for input accounts."""
	if not accounts:
		return 0.0, 0.0
	rows = frappe.db.sql(
		"""
		SELECT SUM(debit) AS debit, SUM(credit) AS credit
		FROM `tabGL Entry`
		WHERE company = %(company)s
		  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND is_cancelled = 0
		  AND account IN %(accounts)s
		""",
		{
			"company": filters.company,
			"from_date": filters.from_date,
			"to_date": filters.to_date,
			"accounts": tuple(accounts),
		},
		as_dict=True,
	)
	row = rows[0] if rows else {}
	return flt(row.get("debit")), flt(row.get("credit"))


def _invoice_totals(filters, doctype, condition=""):
	rows = frappe.db.sql(
		"""
		SELECT SUM(base_net_total) AS net, SUM(base_total_taxes_and_charges) AS tax
		FROM `tab{doctype}`
		WHERE company = %(company)s
		  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND docstatus = 1 {condition}
		""".format(doctype=doctype, condition=condition),
		filters,
		as_dict=True,
	)
	row = rows[0] if rows else {}
	return flt(row.get("net")), flt(row.get("tax"))


def get_data(filters):
	sales_net, sales_tax = _invoice_totals(filters, "Sales Invoice")
	purchase_net, purchase_tax = _invoice_totals(filters, "Purchase Invoice")

	# Deliberately not using `_` as a throwaway here: it is the translation
	# function imported above, and rebinding it to a float breaks every _() call
	# that follows.
	output_debit, output_credit = _gl_movement(filters, _account_names(filters.company, OUTPUT_ACCOUNTS))
	input_debit, input_credit = _gl_movement(filters, _account_names(filters.company, INPUT_ACCOUNTS))

	# Output tax is a credit balance net of any debits (credit notes, reversals);
	# input tax is the mirror image.
	output_tax = flt(output_credit - output_debit, 2)
	input_tax = flt(input_debit - input_credit, 2)

	net_position = flt(output_tax - input_tax, 2)

	data = [
		{"line": "1", "description": _("Total supplies (sales) in the period"), "taxable_value": sales_net, "tax": sales_tax},
		{"line": "2", "description": _("Output tax: VAT + NHIL + GETFund charged"), "taxable_value": None, "tax": output_tax},
		{"line": "", "description": "", "taxable_value": None, "tax": None},
		{"line": "3", "description": _("Total purchases in the period"), "taxable_value": purchase_net, "tax": purchase_tax},
		{"line": "4", "description": _("Input tax recoverable: VAT + NHIL + GETFund"), "taxable_value": None, "tax": input_tax},
		{"line": "", "description": "", "taxable_value": None, "tax": None},
		{
			"line": "5",
			"description": _("NET VAT PAYABLE to GRA") if net_position >= 0 else _("NET VAT CREDIT carried forward"),
			"taxable_value": None,
			"tax": abs(net_position),
		},
	]
	return data


def get_summary(data, filters):
	net_row = data[-1] if data else {}
	return [
		{"label": _("Output Tax"), "value": data[1]["tax"], "datatype": "Currency", "indicator": "Orange"},
		{"label": _("Input Tax"), "value": data[4]["tax"], "datatype": "Currency", "indicator": "Blue"},
		{"label": net_row.get("description", ""), "value": net_row.get("tax", 0), "datatype": "Currency", "indicator": "Red"},
	]
