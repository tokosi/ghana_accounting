# Copyright (c) 2026, FEDCO
# License: MIT

"""
Configuration migration: move setup to a new server without transactions.

The apps rebuild most of their own configuration on install — salary
components, tax accounts, templates, withholding categories, workflows, print
formats, workspaces and number cards all come back from `after_install`. So
this tool only carries what those routines cannot regenerate: the Company
record, users and roles, the chart of accounts as it stands today, and any
settings or customisations made by hand.

Nothing transactional is exported. No invoices, journal entries, payment
entries, salary slips, claims, stock or GL entries.

Usage
    # on the old server
    bench --site old execute migrate_config.export_config --kwargs "{'path':'/tmp/fedco_config'}"

    # copy /tmp/fedco_config to the new server, then
    bench --site new execute migrate_config.import_config --kwargs "{'path':'/tmp/fedco_config'}"
"""

import json
import os

import frappe
from frappe.utils import cint

# Order matters on import: a Company must exist before its accounts, an Account
# before a Salary Component points at it, a Role before a User references it.
EXPORT_PLAN = [
	# --- foundations ---
	("Company", {}, None),
	("Fiscal Year", {}, None),
	("Currency Exchange Settings", {}, None),
	("Department", {}, None),
	("Designation", {}, None),
	("Branch", {}, None),
	("Cost Center", {}, None),
	# --- chart of accounts ---
	("Account", {}, None),
	("Mode of Payment", {}, None),
	("Bank", {}, None),
	("Bank Account", {}, None),
	# --- tax ---
	("Sales Taxes and Charges Template", {}, None),
	("Purchase Taxes and Charges Template", {}, None),
	("Tax Withholding Category", {}, None),
	("Income Tax Slab", {}, None),
	# --- payroll config (no employees, no structures with data) ---
	("Salary Component", {}, None),
	# --- people ---
	("Role", {"is_custom": 1}, None),
	("User", {"user_type": "System User", "name": ("not in", ("Administrator", "Guest"))}, None),
	("Role Profile", {}, None),
	# --- customisation ---
	("Custom Field", {}, None),
	("Property Setter", {}, None),
	("Client Script", {}, None),
	("Server Script", {}, None),
	("Print Format", {"standard": "No"}, None),
	("Workflow", {}, None),
	("Workflow State", {}, None),
	("Workflow Action Master", {}, None),
	("Number Card", {"is_standard": 0}, None),
	("Letter Head", {}, None),
	("Email Template", {}, None),
	("Naming Series", {}, None),
]

# Single doctypes: settings that live as one record.
SINGLES = [
	"Ghana Payroll Settings",
	"Ghana Accounting Settings",
	"Website Settings",
	"System Settings",
	"Global Defaults",
	"Accounts Settings",
	"HR Settings",
	"Payroll Settings",
	"Buying Settings",
	"Selling Settings",
	"Stock Settings",
	"Print Settings",
]

# Fields that must not travel: they are site-specific or secret.
SCRUB_FIELDS = {
	"User": ["password", "new_password", "api_key", "api_secret", "reset_password_key",
	         "last_login", "last_active", "last_ip", "login_after", "login_before"],
	"System Settings": ["encryption_key"],
	"Website Settings": [],
}


def _clean(doc_dict, doctype):
	"""Strip volatile and secret fields before writing to disk."""
	for field in ("modified", "modified_by", "creation", "owner", "idx", "docstatus",
	              "_user_tags", "_comments", "_assign", "_liked_by"):
		doc_dict.pop(field, None)

	for field in SCRUB_FIELDS.get(doctype, []):
		doc_dict.pop(field, None)

	for value in doc_dict.values():
		if isinstance(value, list):
			for row in value:
				if isinstance(row, dict):
					for field in ("modified", "modified_by", "creation", "owner",
					              "parent", "parentfield", "parenttype", "name"):
						row.pop(field, None)
	return doc_dict


@frappe.whitelist()
def export_config(path="/tmp/fedco_config"):
	"""Write every configuration doctype to JSON files under `path`."""
	os.makedirs(path, exist_ok=True)
	summary = {"exported": {}, "skipped": [], "path": path}

	for doctype, filters, _unused in EXPORT_PLAN:
		if not frappe.db.exists("DocType", doctype):
			summary["skipped"].append("{0} (not installed)".format(doctype))
			continue

		try:
			names = frappe.get_all(doctype, filters=filters or {}, pluck="name")
		except Exception as e:
			summary["skipped"].append("{0} ({1})".format(doctype, e))
			continue

		records = []
		for name in names:
			try:
				doc = frappe.get_doc(doctype, name).as_dict()
				records.append(_clean(doc, doctype))
			except Exception:
				continue

		if records:
			_write(path, doctype, records)
			summary["exported"][doctype] = len(records)

	# singles
	single_data = {}
	for doctype in SINGLES:
		if not frappe.db.exists("DocType", doctype):
			continue
		try:
			doc = frappe.get_single(doctype).as_dict()
			single_data[doctype] = _clean(doc, doctype)
		except Exception:
			continue

	if single_data:
		with open(os.path.join(path, "_singles.json"), "w", encoding="utf-8") as f:
			json.dump(single_data, f, indent=1, default=str)
		summary["exported"]["_singles"] = len(single_data)

	# a manifest so the new server can be checked against the old one
	manifest = {
		"site": frappe.local.site,
		"apps": frappe.get_installed_apps(),
		"counts": summary["exported"],
	}
	with open(os.path.join(path, "_manifest.json"), "w", encoding="utf-8") as f:
		json.dump(manifest, f, indent=1, default=str)

	return summary


def _write(path, doctype, records):
	filename = doctype.lower().replace(" ", "_") + ".json"
	with open(os.path.join(path, filename), "w", encoding="utf-8") as f:
		json.dump(records, f, indent=1, default=str)


@frappe.whitelist()
def import_config(path="/tmp/fedco_config", dry_run=0):
	"""
	Load the exported configuration into this site.

	Existing records are updated, not duplicated. Import order follows
	EXPORT_PLAN, because a Company must exist before its accounts and a Role
	before a User that references it.
	"""
	dry_run = cint(dry_run)
	summary = {"created": {}, "updated": {}, "failed": [], "dry_run": bool(dry_run)}

	for doctype, _filters, _unused in EXPORT_PLAN:
		filename = os.path.join(path, doctype.lower().replace(" ", "_") + ".json")
		if not os.path.exists(filename):
			continue
		if not frappe.db.exists("DocType", doctype):
			summary["failed"].append("{0}: doctype not installed here".format(doctype))
			continue

		with open(filename, encoding="utf-8") as f:
			records = json.load(f)

		created = updated = 0
		for record in records:
			name = record.get("name")
			try:
				if name and frappe.db.exists(doctype, name):
					if dry_run:
						updated += 1
						continue
					doc = frappe.get_doc(doctype, name)
					doc.update({k: v for k, v in record.items() if k not in ("name", "doctype")})
					doc.flags.ignore_permissions = True
					doc.flags.ignore_mandatory = True
					doc.flags.ignore_links = True
					doc.save(ignore_permissions=True)
					updated += 1
				else:
					if dry_run:
						created += 1
						continue
					doc = frappe.get_doc(record)
					doc.flags.ignore_permissions = True
					doc.flags.ignore_mandatory = True
					doc.flags.ignore_links = True
					doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
					created += 1
			except Exception as e:
				summary["failed"].append("{0} / {1}: {2}".format(doctype, name, str(e)[:120]))

		if created:
			summary["created"][doctype] = created
		if updated:
			summary["updated"][doctype] = updated

		if not dry_run:
			frappe.db.commit()

	# singles last: they often reference records created above
	singles_file = os.path.join(path, "_singles.json")
	if os.path.exists(singles_file) and not dry_run:
		with open(singles_file, encoding="utf-8") as f:
			singles = json.load(f)
		for doctype, data in singles.items():
			if not frappe.db.exists("DocType", doctype):
				continue
			try:
				doc = frappe.get_single(doctype)
				doc.update({k: v for k, v in data.items() if k not in ("name", "doctype")})
				doc.flags.ignore_permissions = True
				doc.flags.ignore_mandatory = True
				doc.save(ignore_permissions=True)
				summary["updated"][doctype] = 1
			except Exception as e:
				summary["failed"].append("{0}: {1}".format(doctype, str(e)[:120]))
		frappe.db.commit()

	if not dry_run:
		frappe.clear_cache()

	return summary


@frappe.whitelist()
def verify(path="/tmp/fedco_config"):
	"""Compare this site against the manifest from the source server."""
	manifest_file = os.path.join(path, "_manifest.json")
	if not os.path.exists(manifest_file):
		return {"error": "No manifest at {0}".format(path)}

	with open(manifest_file, encoding="utf-8") as f:
		manifest = json.load(f)

	here = frappe.get_installed_apps()
	report = {
		"source_site": manifest.get("site"),
		"apps_missing_here": [a for a in manifest.get("apps", []) if a not in here],
		"apps_extra_here": [a for a in here if a not in manifest.get("apps", [])],
		"counts": {},
	}

	for doctype, expected in (manifest.get("counts") or {}).items():
		if doctype.startswith("_") or not frappe.db.exists("DocType", doctype):
			continue
		actual = frappe.db.count(doctype)
		report["counts"][doctype] = {
			"source": expected,
			"here": actual,
			"ok": actual >= expected,
		}

	# transactional doctypes should be empty on a fresh config-only site
	report["transactions_present"] = {}
	for doctype in ("Sales Invoice", "Purchase Invoice", "Journal Entry", "Payment Entry",
	                "Salary Slip", "Expense Claim", "Stock Entry", "GL Entry"):
		if frappe.db.exists("DocType", doctype):
			count = frappe.db.count(doctype)
			if count:
				report["transactions_present"][doctype] = count

	return report
