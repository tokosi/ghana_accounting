# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""
Expense Claim customisation.

Naming
    {company abbr}-HR-EXP-{YYYY}-#####   e.g. FEDCO-HR-EXP-2026-00001

Approval thresholds
    The approver is chosen from the claim amount rather than picked by the
    claimant, so a staff member cannot route their own claim to a lenient
    approver. Levels are configured in Ghana Accounting Settings.

Layout
    Taxes & Charges, the Accounting tab and the More Info tab are hidden with
    Property Setters rather than by editing ERPNext's own DocType, so they can
    be restored from Customize Form.
"""

import re

import frappe
from frappe import _
from frappe.model.naming import make_autoname
from frappe.utils import cint, flt, nowdate

# Fallback used only when no levels are configured. Real limits belong in
# Ghana Accounting Settings, not in code.
DEFAULT_LEVELS = [
	{"level_name": "Finance Head", "max_amount": 5000, "approver_role": "Expense Approver"},
	{"level_name": "Chief Executive", "max_amount": 200000, "approver_role": "Expense Approver"},
]


# ======================================================================
# naming
# ======================================================================
def autoname_expense_claim(doc, method=None):
	abbr = "XXX"
	if doc.get("company"):
		abbr = frappe.get_cached_value("Company", doc.company, "abbr") or "XXX"
	abbr = re.sub(r"[^A-Za-z0-9]", "", abbr).upper()

	year = str(doc.get("posting_date") or nowdate())[0:4]
	doc.name = make_autoname("{0}-HR-EXP-{1}-.#####".format(abbr, year))


# ======================================================================
# approval thresholds
# ======================================================================
def get_levels():
	"""Approval levels, lowest limit first."""
	try:
		settings = frappe.get_cached_doc("Ghana Accounting Settings")
		rows = settings.get("claim_approval_levels") or []
	except Exception:
		rows = []

	if not rows:
		return [dict(level) for level in DEFAULT_LEVELS]

	levels = [
		{
			"level_name": r.level_name,
			"max_amount": flt(r.max_amount),
			"approver_role": r.get("approver_role"),
			"approver_user": r.get("approver_user"),
			"requires_board": cint(r.get("requires_board")),
		}
		for r in rows
	]
	return sorted(levels, key=lambda x: x["max_amount"] or float("inf"))


def find_level(amount):
	"""
	Lowest level whose limit covers the amount.

	Returns None when the amount exceeds every configured level, which is the
	case that needs board approval.
	"""
	for level in get_levels():
		limit = flt(level.get("max_amount"))
		if limit and flt(amount) <= limit:
			return level
	return None


def resolve_approver(level, claimant_user=None):
	"""
	A named user for the level, else an active holder of its role.

	The claimant is excluded. HRMS treats a claim whose approver is the current
	user as self-approved and submits it immediately, so assigning someone as
	their own approver silently removes the control entirely.
	"""
	if not level:
		return None

	exclude = {"Administrator", "Guest"}
	if claimant_user:
		exclude.add(claimant_user)

	named = level.get("approver_user")
	if named:
		return None if named in exclude else named

	role = level.get("approver_role")
	if not role:
		return None

	users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
	for user in users:
		if user in exclude:
			continue
		if frappe.db.get_value("User", user, "enabled"):
			return user
	return None


def apply_approval_threshold(doc, method=None):
	"""
	Set the approver from the claim amount.

	Overwrites whatever the claimant chose. Letting them keep their own
	selection would make the thresholds advisory rather than a control.
	"""
# HRMS fills total_claimed_amount during its own validate, which can run
	# after this hook. Summing the rows means the approver resolves on a first
	# save rather than being left empty.
	amount = flt(doc.get("total_claimed_amount")) or flt(doc.get("total_sanctioned_amount"))
	if not amount:
		amount = sum(
			flt(r.get("sanctioned_amount")) or flt(r.get("amount"))
			for r in (doc.get("expenses") or [])
		)
	if not amount:
		return

	level = find_level(amount)

	if not level:
		# Above every configured limit: board approval, evidenced by a
		# reference on the claim.
		doc.gh_approval_level = _("Board Approval Required")
		if not (doc.get("gh_board_approval_ref") or "").strip():
			frappe.throw(
				_("This claim of {0} exceeds every approval limit and needs board approval. Record the board minute or resolution reference in <b>Board Approval Reference</b> before submitting.").format(
					frappe.bold("{:,.2f}".format(amount))
				),
				title=_("Board Approval Required"),
			)
		return

	doc.gh_approval_level = level.get("level_name")

	claimant = frappe.db.get_value("Employee", doc.get("employee"), "user_id") if doc.get("employee") else None
	approver = resolve_approver(level, claimant_user=claimant)

	if approver:
		doc.expense_approver = approver
	else:
		frappe.throw(
			_("No approver is configured for the {0} level, or the only candidate is the claimant. Set a different user against that level in Ghana Accounting Settings.").format(
				frappe.bold(level.get("level_name"))
			),
			title=_("Approver Not Configured"),
		)

	# HRMS auto-approves when the approver is the user saving the document.
	# A claimant editing their own draft must never trip that.
	if doc.expense_approver == frappe.session.user and frappe.session.user == claimant:
		frappe.throw(
			_("You cannot be the approver of your own claim."),
			title=_("Self Approval"),
		)


# ======================================================================
# employee defaults
# ======================================================================
@frappe.whitelist()
def get_employee_defaults(user=None):
	"""
	Details for the signed-in user's Employee record.

	Used by the client script to fill the form on load, so the claimant does
	not select themselves from a list of everyone.
	"""
	user = user or frappe.session.user
	name = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
	if not name:
		return {}

	emp = frappe.db.get_value(
		"Employee",
		name,
		["name", "employee_name", "department", "company", "designation", "expense_approver"],
		as_dict=True,
	)
	if not emp:
		return {}

	# Sector / Station is a Ghana custom field; it may not be set on every record.
	emp["gh_sector_station"] = frappe.db.get_value("Employee", name, "gh_sector_station") \
		if frappe.get_meta("Employee").has_field("gh_sector_station") else None

	return emp


# ======================================================================
# validate entry point
# ======================================================================
def resolve_sector(doc):
	"""Collapse the Select and the free-text 'Others' into one printable value."""
	if doc.get("gh_sector_station") == "Others" and doc.get("gh_sector_other"):
		doc.gh_sector_display = doc.gh_sector_other
	else:
		doc.gh_sector_display = doc.get("gh_sector_station")


def validate_expense_claim(doc, method=None):
	resolve_sector(doc)
	apply_approval_threshold(doc)
	keep_draft_while_editing(doc)

	try:
		from ghana_accounting.claim_documents import validate_claim_documents

		# Attaching a file in a grid saves the document, so warning about a
		# missing receipt on every save fires while the claimant is still
		# attaching. The check belongs at submit.
		validate_claim_documents(doc, warn=cint(doc.get("docstatus")) == 1)
	except ImportError:
		pass
	except TypeError:
		# older claim_documents without the warn argument
		if cint(doc.get("docstatus")) == 1:
			validate_claim_documents(doc)


def keep_draft_while_editing(doc):
	"""
	Hold approval_status at Draft while the claimant edits.

	HRMS submits an Expense Claim as soon as approval_status becomes Approved.
	Without this, a save by anyone holding the approver role can submit a claim
	that is still being filled in.
	"""
	if cint(doc.get("docstatus")) != 0:
		return

	claimant = frappe.db.get_value("Employee", doc.get("employee"), "user_id") if doc.get("employee") else None
	if frappe.session.user == claimant and doc.get("approval_status") == "Approved":
		doc.approval_status = "Draft"


# ======================================================================
# layout: hide what is not used
# ======================================================================
HIDE = [
	# Taxes & Charges
	("Expense Claim", "taxes", "hidden", "1"),
	("Expense Claim", "taxes_section", "hidden", "1"),
	("Expense Claim", "total_taxes_and_charges", "hidden", "1"),
	# Accounting tab
	("Expense Claim", "accounting_details_tab", "hidden", "1"),
	("Expense Claim", "accounting_dimensions_section", "hidden", "1"),
	# More Info tab
	("Expense Claim", "more_info_tab", "hidden", "1"),
	# the series field is driven by autoname now
	("Expense Claim", "naming_series", "hidden", "1"),
	# the approver comes from the threshold table, so the claimant never sees
	# or sets it
	("Expense Claim", "expense_approver", "hidden", "1"),
	("Expense Claim", "expense_approver", "reqd", "0"),
]


def apply_layout():
	"""Hide unused sections. Reversible from Customize Form."""
	meta = frappe.get_meta("Expense Claim")
	applied, skipped = [], []

	for doctype, fieldname, prop, value in HIDE:
		if not meta.has_field(fieldname):
			skipped.append(fieldname)
			continue
		try:
			frappe.make_property_setter(
				{
					"doctype": doctype,
					"fieldname": fieldname,
					"property": prop,
					"value": value,
					"property_type": "Check",
					"doctype_or_field": "DocField",
				},
				ignore_validate=True,
			)
			applied.append(fieldname)
		except Exception:
			frappe.log_error(
				title="Expense Claim layout: {0}".format(fieldname),
				message=frappe.get_traceback(),
			)

	frappe.db.commit()
	return {"hidden": applied, "not_present_on_this_version": skipped}


@frappe.whitelist()
def setup_expense_claim():
	"""Fields plus layout, in one call."""
	from ghana_accounting.expense_claim_fields import install_fields

	created = install_fields()
	layout = apply_layout()
	frappe.clear_cache()
	return {"custom_fields": created, "layout": layout}
