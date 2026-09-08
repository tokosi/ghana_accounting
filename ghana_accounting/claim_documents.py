# Copyright (c) 2026, Ghana Accounting Contributors
# License: MIT

"""
Supporting documents on Expense Claim.

Three things happen here:

1. The claimant lists each supporting document with its type, reference and
   file, rather than dropping loose files into the sidebar where nobody can
   tell a receipt from a quotation.

2. The approver sees that list on the form with working links, and can tick
   each one off as sighted.

3. `validate` writes a plain-text summary onto the document so the print format
   can state what was attached. The Jinja print sandbox cannot query the File
   table, so the summary has to exist as a field by the time the voucher is
   printed — the same reason the payslip stores its PAYE band breakdown.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

# Types that count as proof of spend. A claim carrying only a quotation or a
# photograph has not evidenced the expenditure, so those do not satisfy the
# "receipt required" rule.
PROOF_TYPES = {"Receipt", "Invoice", "Evidence of Work Done", "Waybill", "Delivery Note"}


def validate_claim_documents(doc, method=None):
	"""Hooked on Expense Claim validate."""
	rows = doc.get("gh_documents") or []

	# Files attached the ordinary way still count; a claimant who used the
	# sidebar should not be told they attached nothing.
	native = get_native_attachments(doc)

	types = []
	for row in rows:
		if not row.attachment:
			frappe.throw(
				_("Row {0} in Supporting Documents has no file attached.").format(row.idx)
			)
		label = row.document_type or _("Document")
		if row.reference:
			label = "{0} {1}".format(label, row.reference)
		types.append(label)

	summary_parts = list(types)
	if native:
		summary_parts.append(
			_("{0} file(s) attached to the record").format(len(native))
		)

	doc.gh_has_attachments = 1 if (rows or native) else 0
	doc.gh_attachment_count = len(rows) + len(native)
	doc.gh_attachment_summary = "; ".join(summary_parts) if summary_parts else ""

	# Keep the free-text field on the printed voucher in step, unless someone
	# has deliberately typed something else there.
	if not doc.get("gh_supporting_documents") and summary_parts:
		doc.gh_supporting_documents = doc.gh_attachment_summary

	warn_if_no_proof(doc, rows, native)


def get_native_attachments(doc):
	"""Files attached to the document through the sidebar."""
	if not doc.get("name") or doc.get("__islocal"):
		return []
	try:
		return frappe.get_all(
			"File",
			filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name},
			fields=["file_name", "file_url"],
		)
	except Exception:
		return []


def warn_if_no_proof(doc, rows, native):
	"""
	Warn rather than block.

	A claim can legitimately have no receipt — that is exactly what the
	"Supplier Contact (if no receipts)" field on the paper form is for. Blocking
	the save would push people to attach something irrelevant just to get past
	the check, which is worse than an honest note on the voucher.
	"""
	has_proof = any((r.document_type in PROOF_TYPES) for r in rows)
	if has_proof or native:
		return

	if doc.get("gh_supplier_contact"):
		return

	frappe.msgprint(
		_(
			"No receipt, invoice or evidence of work is attached. Either attach one, or record the supplier's phone number in <b>Supplier Contact</b> so the claim can be verified."
		),
		indicator="orange",
		title=_("Supporting Document Missing"),
	)


@frappe.whitelist()
def get_claim_documents(expense_claim):
	"""
	Documents for the approver's review panel.

	Returns both the itemised rows and anything attached to the record, so the
	approver sees everything in one place regardless of how it was uploaded.
	"""
	if not frappe.has_permission("Expense Claim", "read", doc=expense_claim):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Expense Claim", expense_claim)

	items = [
		{
			"idx": r.idx,
			"document_type": r.document_type,
			"reference": r.reference,
			"file_url": r.attachment,
			"amount": flt(r.amount),
			"verified": cint(r.verified),
			"remarks": r.remarks,
			"source": "listed",
		}
		for r in (doc.get("gh_documents") or [])
	]

	for f in get_native_attachments(doc):
		items.append(
			{
				"idx": None,
				"document_type": _("Attached File"),
				"reference": f.get("file_name"),
				"file_url": f.get("file_url"),
				"amount": 0,
				"verified": 0,
				"remarks": None,
				"source": "sidebar",
			}
		)

	return {
		"claim": doc.name,
		"employee_name": doc.get("employee_name"),
		"total": flt(doc.get("total_claimed_amount")),
		"documents": items,
		"count": len(items),
	}


@frappe.whitelist()
def mark_verified(expense_claim, row_idx, verified=1):
	"""Approver ticks a document as sighted."""
	if not frappe.has_permission("Expense Claim", "write", doc=expense_claim):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc = frappe.get_doc("Expense Claim", expense_claim)
	for row in doc.get("gh_documents") or []:
		if str(row.idx) == str(row_idx):
			row.db_set("verified", cint(verified))
			break

	frappe.db.commit()
	return {"row": row_idx, "verified": cint(verified)}
