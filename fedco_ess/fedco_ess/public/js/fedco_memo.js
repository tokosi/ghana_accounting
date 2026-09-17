// Copyright (c) 2026, FEDCO
// License: MIT

frappe.ui.form.on("FEDCO Memo", {
	setup(frm) {
		frm.set_query("employee", () => ({ filters: { status: "Active" } }));
	},

	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Print Memo"), () => {
				frm.print_doc();
			});
		}
	},

	employee(frm) {
		if (!frm.doc.employee) return;
		frappe.db.get_value("Employee", frm.doc.employee, ["employee_name", "designation", "company"])
			.then((r) => {
				const d = r.message || {};
				frm.set_value("employee_name", d.employee_name);
				if (!frm.doc.signatory_name) frm.set_value("signatory_name", d.employee_name);
				if (!frm.doc.signatory_designation) frm.set_value("signatory_designation", d.designation);
				if (!frm.doc.memo_from && d.designation) {
					frm.set_value("memo_from", (d.designation || "").toUpperCase());
				}
				if (!frm.doc.company) frm.set_value("company", d.company);
			});
	},
});

// Keep the costed table adding up as the user types.
frappe.ui.form.on("FEDCO Memo Item", {
	qty: (frm, cdt, cdn) => fedco_memo_row(frm, cdt, cdn),
	unit_price: (frm, cdt, cdn) => fedco_memo_row(frm, cdt, cdn),
	items_remove: (frm) => fedco_memo_total(frm),
});

function fedco_memo_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "sub_total", flt(row.qty) * flt(row.unit_price));
	fedco_memo_total(frm);
}

function fedco_memo_total(frm) {
	const total = (frm.doc.items || []).reduce((a, r) => a + flt(r.sub_total), 0);
	frm.set_value("total_amount", total);
}
