// Copyright (c) 2026, Ghana Payroll Contributors
// License: MIT

frappe.ui.form.on("Ghana Accounting Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Run Accounting Setup"), () => {
			frappe.confirm(
				__("Create the tax accounts, templates, withholding categories and workflows?"),
				() => {
					frappe.call({
						method: "ghana_accounting.ghana_accounting.doctype.ghana_accounting_settings.ghana_accounting_settings.run_setup",
						freeze: true,
						freeze_message: __("Configuring Ghana accounting..."),
						callback: (r) => {
							const res = r.message || {};
							const companies = (res.companies || []).join(", ") || __("none");
							frappe.msgprint({
								title: __("Setup Complete"),
								indicator: res.skipped ? "orange" : "green",
								message: res.skipped
									? res.skipped
									: __("Configured for: {0}", [companies]),
							});
						},
					});
				}
			);
		}, __("Setup"));

		frm.add_custom_button(__("Restore Statutory Levies"), () => {
			frappe.call({
				method: "ghana_accounting.ghana_accounting.doctype.ghana_accounting_settings.ghana_accounting_settings.seed_default_levies",
				freeze: true,
				callback: () => {
					frappe.show_alert({ message: __("Levy structure restored"), indicator: "green" });
					frm.reload_doc();
				},
			});
		}, __("Setup"));

		frm.dashboard.clear_headline();
		const total = (frm.doc.levy_rates || [])
			.filter((r) => r.charge_type === "On Net Total")
			.reduce((a, r) => a + flt(r.rate), 0);

		if (!frm.doc.enabled) {
			frm.dashboard.set_headline(__("Ghana Accounting is <b>disabled</b>."));
		} else {
			frm.dashboard.set_headline(
				__("Combined indirect tax on net total: <b>{0}%</b>", [total.toFixed(2)])
			);
		}
	},

	enable_jv_workflow(frm) {
		if (frm.doc.enable_jv_workflow) {
			frappe.msgprint({
				title: __("Test Payroll First"),
				indicator: "orange",
				message: __(
					"Payroll Entry submits its accrual journal entry programmatically. An active Journal Entry workflow can leave that journal stranded in Draft and stop payroll posting. Run a test Payroll Entry immediately after saving."
				),
			});
		}
	},
});
