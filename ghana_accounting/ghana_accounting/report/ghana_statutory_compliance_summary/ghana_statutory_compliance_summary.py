# Copyright (c) 2026, Ghana Payroll Contributors
# License: MIT

"""
Ghana Statutory Compliance Summary.

Single view of what is owed to GRA and SSNIT for a period, with the statutory
filing deadline for each. Balances come from the GL, so they reflect what was
actually posted, not what payroll or the tax engine calculated.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_last_day, getdate

# (account name, obligation, authority, day of the following month it is due)
#
# Payroll lines appear only when the matching ledger account exists, so this
# report is correct on a site without the Ghana Payroll app rather than showing
# empty rows for obligations that do not apply.
OBLIGATIONS = [
	("PAYE Payable", "PAYE", "Ghana Revenue Authority", 15),
	("SSNIT Payable", "SSNIT Tier 1 & 2", "SSNIT", 14),
	("Provident Fund Payable", "Provident Fund (Tier 3)", "Trustee", 14),
	("WHT Payable - Suppliers", "Withholding Tax", "Ghana Revenue Authority", 15),
	("VAT Output Payable", "VAT (output)", "Ghana Revenue Authority", 30),
	("NHIL Output Payable", "NHIL", "Ghana Revenue Authority", 30),
	("GETFund Output Payable", "GETFund Levy", "Ghana Revenue Authority", 30),
]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company or not filters.from_date or not filters.to_date:
		frappe.throw(_("Company and date range are required."))

	data = get_data(filters)
	return get_columns(), data, None, get_chart(data), get_summary(data)


def get_columns():
	return [
		{"label": _("Obligation"), "fieldname": "obligation", "fieldtype": "Data", "width": 200},
		{"label": _("Authority"), "fieldname": "authority", "fieldtype": "Data", "width": 200},
		{"label": _("Account"), "fieldname": "account", "fieldtype": "Link", "options": "Account", "width": 240},
		{"label": _("Accrued in Period"), "fieldname": "accrued", "fieldtype": "Currency", "width": 150},
		{"label": _("Paid in Period"), "fieldname": "paid", "fieldtype": "Currency", "width": 140},
		{"label": _("Closing Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 150},
		{"label": _("Due By"), "fieldname": "due_by", "fieldtype": "Date", "width": 110},
	]


def _due_date(to_date, day):
	period_end = getdate(to_date)
	following = add_days(get_last_day(period_end), 1)
	try:
		return following.replace(day=day)
	except ValueError:
		return get_last_day(following)


def get_data(filters):
	data = []
	for account_name, obligation, authority, due_day in OBLIGATIONS:
		account = frappe.db.get_value(
			"Account", {"company": filters.company, "account_name": account_name}, "name"
		)
		if not account:
			continue

		rows = frappe.db.sql(
			"""
			SELECT SUM(credit) AS credit, SUM(debit) AS debit
			FROM `tabGL Entry`
			WHERE company = %(company)s AND account = %(account)s
			  AND is_cancelled = 0
			  AND posting_date BETWEEN %(from_date)s AND %(to_date)s
			""",
			{"company": filters.company, "account": account, "from_date": filters.from_date, "to_date": filters.to_date},
			as_dict=True,
		)
		movement = rows[0] if rows else {}

		closing = frappe.db.sql(
			"""
			SELECT SUM(credit) - SUM(debit) AS balance
			FROM `tabGL Entry`
			WHERE company = %(company)s AND account = %(account)s
			  AND is_cancelled = 0 AND posting_date <= %(to_date)s
			""",
			{"company": filters.company, "account": account, "to_date": filters.to_date},
			as_dict=True,
		)

		data.append(
			{
				"obligation": obligation,
				"authority": authority,
				"account": account,
				"accrued": flt(movement.get("credit"), 2),
				"paid": flt(movement.get("debit"), 2),
				"balance": flt((closing[0].get("balance") if closing else 0), 2),
				"due_by": _due_date(filters.to_date, due_day),
			}
		)
	return data


def get_chart(data):
	rows = [d for d in data if d.get("balance")]
	if not rows:
		return None
	return {
		"data": {
			"labels": [d["obligation"] for d in rows],
			"datasets": [{"name": _("Outstanding"), "values": [d["balance"] for d in rows]}],
		},
		"type": "bar",
		"colors": ["#c0392b"],
	}


def get_summary(data):
	return [
		{
			"label": _("Accrued in Period"),
			"value": sum(d.get("accrued") or 0 for d in data),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Total Outstanding"),
			"value": sum(d.get("balance") or 0 for d in data),
			"datatype": "Currency",
			"indicator": "Red",
		},
	]
