# Copyright (c) 2026, FEDCO
# License: MIT

"""
Internal memo.

Numbered MEMO/{company abbr}/MM/YYYY/#####, matching the voucher convention so
a memo can be referenced the same way a JV or PV can.
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt, nowdate


class FEDCOMemo(Document):
	def autoname(self):
		posting = self.memo_date or nowdate()
		month, year = str(posting)[5:7], str(posting)[0:4]
		abbr = re.sub(
			r"[^A-Za-z0-9]", "", (frappe.get_cached_value("Company", self.company, "abbr") or "XXX")
		).upper()
		self.name = make_autoname("MEMO/{0}/{1}/{2}/.#####".format(abbr, month, year))

	def validate(self):
		self.set_signatory()
		self.calculate_items()
		self.validate_routing()

	def set_signatory(self):
		"""Default the signature block to the employee raising the memo."""
		if self.employee and not self.signatory_name:
			self.signatory_name = frappe.db.get_value("Employee", self.employee, "employee_name")
		if self.employee and not self.signatory_designation:
			self.signatory_designation = frappe.db.get_value("Employee", self.employee, "designation")

	def calculate_items(self):
		total = 0.0
		for row in self.get("items") or []:
			row.sub_total = flt(flt(row.qty) * flt(row.unit_price), 2)
			total += row.sub_total
		self.total_amount = flt(total, 2)

		# A costed table with nothing in it prints as an empty box, so the
		# flag is cleared rather than left on.
		if cint(self.show_items) and not (self.get("items") or []):
			self.show_items = 0

	def validate_routing(self):
		if self.through and self.through.strip().lower() == (self.memo_to or "").strip().lower():
			frappe.throw(
				_("Through and To are the same office. Remove one of them."),
				title=_("Routing"),
			)


@frappe.whitelist()
def make_memo_from_employee(employee=None):
	"""Prefill a memo for the signed-in employee. Used by the ESS portal."""
	user = frappe.session.user
	employee = employee or frappe.db.get_value("Employee", {"user_id": user}, "name")
	if not employee:
		frappe.throw(_("No Employee record is linked to your user account."))

	emp = frappe.get_doc("Employee", employee)
	memo = frappe.new_doc("FEDCO Memo")
	memo.company = emp.company
	memo.employee = emp.name
	memo.employee_name = emp.employee_name
	memo.memo_date = nowdate()
	memo.memo_from = (emp.designation or "").upper()
	memo.signatory_name = emp.employee_name
	memo.signatory_designation = emp.designation
	return memo.as_dict()
