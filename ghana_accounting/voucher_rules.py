# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""
Journal Voucher and Payment Voucher rules.

Naming
    JV/{company abbr}/MM/YYYY/#####
    PV/{company abbr}/{bank abbr}/MM/YYYY/#####

The serial resets per prefix, so each company, bank and month counts from 1.
That is `make_autoname` behaviour, not something enforced here.

Validation
    · a voucher must balance before it can be saved, not just before submit
    · every line carries a text reference
    · Transaction Description is mandatory
    · Reference Date is optional
    · a Payment Voucher is dated today, and its cheque date matches
"""

import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt, nowdate

# A Journal Entry of these voucher types is treated as a Payment Voucher.
PAYMENT_TYPES = {"Bank Entry", "Cash Entry", "Credit Card Entry"}


# ======================================================================
# naming
# ======================================================================
def _abbr(company):
	"""Company abbreviation, uppercased and stripped of separators."""
	if not company:
		return "XXX"
	abbr = frappe.get_cached_value("Company", company, "abbr") or company[:4]
	return re.sub(r"[^A-Za-z0-9]", "", abbr).upper() or "XXX"


def _bank_abbr(doc):
	"""
	Short code for the bank the payment leaves from.

	Preference: the code the user typed, then the Bank linked to the credited
	bank account, then the account name itself. Falls back to CASH so a cash
	payment still names cleanly rather than failing to save.
	"""
	typed = (doc.get("gh_bank_code") or "").strip()
	if typed:
		return re.sub(r"[^A-Za-z0-9]", "", typed).upper()

	for row in doc.get("accounts") or []:
		if not flt(row.get("credit_in_account_currency")):
			continue

		account = row.get("account")
		if not account:
			continue

		account_type = frappe.get_cached_value("Account", account, "account_type")
		if account_type not in ("Bank", "Cash"):
			continue

		if account_type == "Cash":
			return "CASH"

		# Bank Account -> Bank gives a proper institution name to abbreviate.
		bank_account = frappe.db.get_value(
			"Bank Account", {"account": account}, ["bank"], as_dict=True
		)
		if bank_account and bank_account.get("bank"):
			return _shorten(bank_account.get("bank"))

		return _shorten(frappe.get_cached_value("Account", account, "account_name") or account)

	return "CASH"


def _shorten(name, length=4):
	"""
	Initials for a multi-word institution, otherwise the leading letters.

	"Universal Merchant Bank" -> UMB. "Access Bank" -> AB. "Ecobank" -> ECOB.
	"""
	cleaned = re.sub(r"[^A-Za-z0-9 ]", " ", name or "").strip()
	# "Bank" is kept: Universal Merchant Bank abbreviates to UMB, not UM.
	# Only legal-form suffixes are dropped.
	words = [
		w for w in cleaned.split()
		if w.lower() not in ("limited", "ltd", "plc", "company", "co", "the")
	]
	if len(words) >= 2:
		return "".join(w[0] for w in words)[:length].upper()
	base = words[0] if words else re.sub(r"[^A-Za-z0-9]", "", cleaned)
	return base[:length].upper() or "BANK"


def is_payment_voucher(doc):
	explicit = doc.get("gh_voucher_class")
	if explicit:
		return explicit == "Payment Voucher"
	return doc.get("voucher_type") in PAYMENT_TYPES


def autoname_journal_entry(doc, method=None):
	"""
	Build the voucher number.

	Hooked on `autoname`, so it runs before the document is written and the
	number is final from the first save.
	"""
	posting = doc.get("posting_date") or nowdate()
	try:
		month = str(posting)[5:7]
		year = str(posting)[0:4]
	except Exception:
		month, year = nowdate()[5:7], nowdate()[0:4]

	abbr = _abbr(doc.get("company"))

	if is_payment_voucher(doc):
		bank = _bank_abbr(doc)
		doc.name = make_autoname("PV/{0}/{1}/{2}/{3}/.#####".format(abbr, bank, month, year))
	else:
		doc.name = make_autoname("JV/{0}/{1}/{2}/.#####".format(abbr, month, year))


# ======================================================================
# validation
# ======================================================================
def validate_journal_entry(doc, method=None):
	set_voucher_class(doc)
	enforce_payment_voucher_dates(doc)
	enforce_balanced(doc)
	enforce_line_references(doc)
	enforce_transaction_description(doc)
	enforce_payable_direction(doc)


def set_voucher_class(doc):
	try:
		has_class = doc.meta.has_field("gh_voucher_class")
	except Exception:
		has_class = True
	if has_class and not doc.get("gh_voucher_class"):
		doc.gh_voucher_class = (
			"Payment Voucher" if doc.get("voucher_type") in PAYMENT_TYPES else "Journal Voucher"
		)


def enforce_payment_voucher_dates(doc):
	"""
	A Payment Voucher is dated today and its cheque date matches.

	Only applied while the document is a draft. Rewriting the posting date of a
	submitted voucher would move it into a different period and silently
	misstate the accounts.
	"""
	if not is_payment_voucher(doc):
		return
	if cint(doc.get("docstatus")) != 0:
		return

	today = nowdate()
	doc.posting_date = today
	try:
		if doc.meta.has_field("cheque_date"):
			doc.cheque_date = today
	except Exception:
		doc.cheque_date = today


def enforce_balanced(doc):
	"""
	Block an unbalanced voucher at save, not only at submit.

	Stock ERPNext lets a draft sit out of balance. Holding a half-entered
	voucher in the system is how a difference reaches month end unnoticed.
	"""
	total_debit = sum(flt(r.get("debit_in_account_currency")) for r in (doc.get("accounts") or []))
	total_credit = sum(flt(r.get("credit_in_account_currency")) for r in (doc.get("accounts") or []))
	difference = flt(total_debit - total_credit, 2)

	if not (doc.get("accounts") or []):
		frappe.throw(_("Add at least one account row before saving."))

	if difference:
		frappe.throw(
			_("This voucher does not balance. Debit {0} against credit {1}, a difference of {2}. Correct the rows before saving.").format(
				frappe.bold("{:,.2f}".format(total_debit)),
				frappe.bold("{:,.2f}".format(total_credit)),
				frappe.bold("{:,.2f}".format(difference)),
			),
			title=_("Voucher Out of Balance"),
		)


def enforce_line_references(doc):
	"""Every line needs a free-text reference."""
	child_meta = frappe.get_meta("Journal Entry Account")
	if not child_meta.has_field("gh_line_reference"):
		return

	missing = [
		str(r.idx) for r in (doc.get("accounts") or []) if not (r.get("gh_line_reference") or "").strip()
	]
	if missing:
		frappe.throw(
			_("Reference is required on every line. Missing on row(s): {0}.").format(", ".join(missing)),
			title=_("Line Reference Missing"),
		)


def enforce_transaction_description(doc):
	if not (doc.get("user_remark") or "").strip():
		frappe.throw(
			_("Transaction Description is required."), title=_("Description Missing")
		)


def enforce_payable_direction(doc):
	"""
	A Payment Voucher pays out; it never receives.

	Money leaving means the bank or cash account is credited. A PV that debits
	the bank is a receipt and has been raised on the wrong voucher type, so it
	is stopped rather than posted under a PV number.
	"""
	if not is_payment_voucher(doc):
		return

	bank_debits = 0.0
	bank_credits = 0.0
	for row in doc.get("accounts") or []:
		account = row.get("account")
		if not account:
			continue
		if frappe.get_cached_value("Account", account, "account_type") not in ("Bank", "Cash"):
			continue
		bank_debits += flt(row.get("debit_in_account_currency"))
		bank_credits += flt(row.get("credit_in_account_currency"))

	if bank_debits and not bank_credits:
		frappe.throw(
			_("A Payment Voucher pays money out, so the bank or cash account must be credited. This voucher debits it, which is a receipt. Change the voucher type, or reverse the rows."),
			title=_("Payment Voucher Must Be Payable"),
		)


# ======================================================================
# one-time setup
# ======================================================================
def apply_property_setters():
	"""
	Field-level rules that belong to the site rather than to code.

	Property Setters are used so ERPNext's own field definitions stay intact
	and the changes can be undone from Customize Form.
	"""
	setters = [
		# Transaction Description, mandatory
		("Journal Entry", "user_remark", "label", "Transaction Description", "Data"),
		("Journal Entry", "user_remark", "reqd", "1", "Check"),
		# Reference Date optional
		("Journal Entry", "cheque_date", "reqd", "0", "Check"),
		("Journal Entry", "cheque_no", "reqd", "0", "Check"),
		# naming is built in code, so the series field must not fight it
		("Journal Entry", "naming_series", "hidden", "1", "Check"),
	]

	for doctype, fieldname, prop, value, prop_type in setters:
		try:
			frappe.make_property_setter(
				{
					"doctype": doctype,
					"fieldname": fieldname,
					"property": prop,
					"value": value,
					"property_type": prop_type,
					"doctype_or_field": "DocField",
				},
				ignore_validate=True,
			)
		except Exception:
			frappe.log_error(
				title="Ghana Accounting: property setter {0}.{1}".format(doctype, fieldname),
				message=frappe.get_traceback(),
			)

	ensure_reference_type_option()
	frappe.db.commit()


def ensure_reference_type_option(option="Purchase Invoice"):
	"""Make sure the line reference type offers Purchase Invoice."""
	try:
		field = frappe.get_meta("Journal Entry Account").get_field("reference_type")
		if not field or not field.options:
			return
		options = [o.strip() for o in field.options.split("\n")]
		if option in options:
			return
		options.append(option)
		frappe.make_property_setter(
			{
				"doctype": "Journal Entry Account",
				"fieldname": "reference_type",
				"property": "options",
				"value": "\n".join(options),
				"property_type": "Text",
				"doctype_or_field": "DocField",
			},
			ignore_validate=True,
		)
	except Exception:
		frappe.log_error(
			title="Ghana Accounting: reference_type option", message=frappe.get_traceback()
		)


@frappe.whitelist()
def setup_voucher_rules():
	"""Run the one-time field configuration. Safe to re-run."""
	apply_property_setters()
	return {
		"property_setters": "applied",
		"note": "Existing vouchers keep their current numbers; the new format applies to new ones.",
	}


@frappe.whitelist()
def preview_name(company=None, voucher_type="Bank Entry", posting_date=None):
	"""Show what the next voucher number would look like, without creating one."""
	posting = posting_date or nowdate()
	abbr = _abbr(company)
	month, year = str(posting)[5:7], str(posting)[0:4]

	if voucher_type in PAYMENT_TYPES:
		return "PV/{0}/{{bank}}/{1}/{2}/00001".format(abbr, month, year)
	return "JV/{0}/{1}/{2}/00001".format(abbr, month, year)
