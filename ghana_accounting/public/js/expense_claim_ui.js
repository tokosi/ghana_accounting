// Copyright (c) 2026, Ghana Accounting Contributors
// License: MIT

/**
 * Expense Claim front-end changes.
 *
 * · fills the claimant's own details on load, so nobody picks themselves
 *   from a list of everyone
 * · removes the bulk CSV "Upload" button under the child grids, which is a
 *   data-import tool rather than a way to attach a receipt
 * · keeps a per-row delete on those grids
 * · shows the approval level and what it means
 */

frappe.ui.form.on("Expense Claim", {
	onload(frm) {
		if (frm.is_new()) {
			fedco_fill_employee(frm);
		}
	},

	refresh(frm) {
		fedco_tidy_grids(frm);
		fedco_show_level(frm);

	},

	gh_sector_station(frm) {
		if (frm.doc.gh_sector_station !== "Others") {
			frm.set_value("gh_sector_other", null);
		}
	},

	employee(frm) {
		if (!frm.doc.employee) return;
		frappe.db
			.get_value("Employee", frm.doc.employee, [
				"employee_name",
				"department",
				"company",
				"gh_sector_station",
			])
			.then((r) => {
				const d = r.message || {};
				frm.set_value("employee_name", d.employee_name);
				if (d.department) frm.set_value("department", d.department);
				if (d.company) frm.set_value("company", d.company);
				if (d.gh_sector_station && frm.fields_dict.gh_sector_station) {
					frm.set_value("gh_sector_station", d.gh_sector_station);
				}
			});
	},

	total_claimed_amount(frm) {
		fedco_show_level(frm);
	},
});

/** Prefill from the signed-in user's Employee record. */
function fedco_fill_employee(frm) {
	frappe.call({
		method: "ghana_accounting.expense_claim_rules.get_employee_defaults",
		callback: (r) => {
			const d = r.message;
			if (!d || !d.name) {
				frappe.show_alert({
					message: __("Your user is not linked to an Employee record. Ask HR to set User ID."),
					indicator: "orange",
				});
				return;
			}
			frm.set_value("employee", d.name);
			frm.set_value("employee_name", d.employee_name);
			if (d.department) frm.set_value("department", d.department);
			if (d.company) frm.set_value("company", d.company);
			if (d.gh_sector_station && frm.fields_dict.gh_sector_station) {
				frm.set_value("gh_sector_station", d.gh_sector_station);
			}
		},
	});
}

/**
 * Remove the bulk CSV upload from the child grids.
 *
 * Frappe re-renders grids on refresh, so this runs on every refresh rather
 * than once on load.
 */
function fedco_tidy_grids(frm) {
	["expenses", "advances"].forEach((fieldname) => {
		const field = frm.fields_dict[fieldname];
		if (!field || !field.grid) return;

		// the CSV importer, not an attachment control
		field.grid.wrapper.find(".grid-upload, .btn-grid-upload").hide();
		field.grid.wrapper
			.find("button")
			.filter((i, el) => $(el).text().trim() === __("Upload"))
			.hide();

		// row delete stays available without selecting a checkbox first
		if (field.grid.df) {
			field.grid.df.cannot_delete_rows = 0;
		}
		field.grid.only_sortable && field.grid.only_sortable(false);
	});
}

/** Explain which approval level the current amount falls into. */
function fedco_show_level(frm) {
	frm.dashboard.clear_headline();
	const amount = flt(frm.doc.total_claimed_amount);
	if (!amount) return;

	if (frm.doc.gh_approval_level) {
		const board = frm.doc.gh_approval_level.indexOf("Board") !== -1;
		frm.dashboard.set_headline(
			board
				? __(
						"This claim of {0} exceeds every approval limit. A board reference is required before it can be submitted.",
						[format_currency(amount, frm.doc.currency)]
				  )
				: __("Approval level: <b>{0}</b>. Routed automatically.", [
						frm.doc.gh_approval_level,
				  ])
		);
	}
}
