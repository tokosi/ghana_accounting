# Copyright (c) 2026, Ghana Payroll Contributors
# License: MIT

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

# Act 1151, effective 1 January 2026: all three levies charge on the same
# taxable value (20% combined) and all three are recoverable as input tax.
DEFAULT_LEVIES = [
	{"levy_name": "NHIL", "rate": 2.5, "charge_type": "On Net Total", "recoverable": 1},
	{"levy_name": "GETFund Levy", "rate": 2.5, "charge_type": "On Net Total", "recoverable": 1},
	{"levy_name": "VAT", "rate": 15.0, "charge_type": "On Net Total", "recoverable": 1},
]


class GhanaAccountingSettings(Document):
	def validate(self):
		self.validate_levies()
		self.warn_on_jv_workflow()

	def validate_levies(self):
		for row in self.levy_rates or []:
			if flt(row.rate) < 0 or flt(row.rate) > 100:
				frappe.throw(_("Row {0}: rate must be between 0 and 100.").format(row.idx))

		compounding = [r for r in (self.levy_rates or []) if r.charge_type != "On Net Total"]
		if compounding:
			frappe.msgprint(
				_(
					"{0} of your levy rows compound on a previous row. Since 1 January 2026 VAT, NHIL and GETFund are charged on the same taxable value, so compounding overstates the tax."
				).format(len(compounding)),
				indicator="orange",
				title=_("Check Levy Structure"),
			)

		total = sum(flt(r.rate) for r in (self.levy_rates or []) if r.charge_type == "On Net Total")
		if total and abs(total - 20.0) > 0.01:
			frappe.msgprint(
				_("Levies on net total come to {0}%. The standard combined rate is 20%.").format(total),
				indicator="orange",
			)

	def warn_on_jv_workflow(self):
		if not cint(self.enable_jv_workflow):
			return
		if self.has_value_changed("enable_jv_workflow"):
			frappe.msgprint(
				_(
					"The Journal Voucher workflow is now active. Run a test Payroll Entry before relying on it: payroll submits its accrual journal programmatically and an active workflow can leave that journal in Draft."
				),
				indicator="red",
				title=_("Test Payroll Before Relying On This"),
			)

	def on_update(self):
		frappe.clear_cache(doctype="Ghana Accounting Settings")


@frappe.whitelist()
def seed_default_levies():
	"""Restore the statutory VAT / NHIL / GETFund structure."""
	doc = frappe.get_doc("Ghana Accounting Settings")
	doc.levy_rates = []
	for levy in DEFAULT_LEVIES:
		doc.append("levy_rates", levy)
	doc.flags.ignore_permissions = True
	doc.save(ignore_permissions=True)
	return len(DEFAULT_LEVIES)


@frappe.whitelist()
def run_setup():
	"""Re-run the accounting setup from the settings screen."""
	from ghana_accounting.install import setup_accounting

	return setup_accounting()
