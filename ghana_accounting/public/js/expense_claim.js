// Copyright (c) 2026, Ghana Accounting Contributors
// License: MIT

/**
 * Supporting-document affordances on Expense Claim.
 *
 * The claimant gets a quick way to add a document. The approver gets a banner
 * showing how many documents are attached and a panel to open each one and tick
 * it off — so approving does not mean hunting through the sidebar.
 */

frappe.ui.form.on("Expense Claim", {
	refresh(frm) {
		if (frm.is_new()) return;

		fedco_claim_banner(frm);

		frm.add_custom_button(__("Supporting Documents"), () => {
			fedco_show_documents(frm);
		});

		// Approvers get it as the primary action, since reviewing the evidence
		// is the whole point of the approval step.
		if (fedco_is_approver(frm)) {
			frm.page.set_secondary_action(__("Review Documents"), () => {
				fedco_show_documents(frm);
			});
		}
	},

	gh_documents(frm) {
		fedco_claim_banner(frm);
	},
});

function fedco_is_approver(frm) {
	const approver = frm.doc.expense_approver;
	return approver && approver === frappe.session.user && frm.doc.docstatus === 0;
}

function fedco_claim_banner(frm) {
	frm.dashboard.clear_headline();

	const listed = (frm.doc.gh_documents || []).length;
	const total = frm.doc.gh_attachment_count || listed;

	if (!total) {
		frm.dashboard.set_headline(
			__("No supporting documents attached. Add a receipt or invoice, or record the supplier's phone number.")
		);
		return;
	}

	const verified = (frm.doc.gh_documents || []).filter((d) => d.verified).length;
	frm.dashboard.set_headline(
		__("{0} supporting document(s) attached &mdash; {1} verified.", [total, verified])
	);
}

function fedco_show_documents(frm) {
	frappe.call({
		method: "ghana_accounting.claim_documents.get_claim_documents",
		args: { expense_claim: frm.doc.name },
		freeze: true,
		callback: (r) => {
			const data = r.message;
			if (!data || !data.count) {
				frappe.msgprint({
					title: __("Supporting Documents"),
					indicator: "orange",
					message: __("Nothing has been attached to this claim yet."),
				});
				return;
			}

			const canVerify = fedco_is_approver(frm);

			const rows = data.documents
				.map((d) => {
					const amount = d.amount
						? format_currency(d.amount, frm.doc.currency)
						: "&mdash;";
					const badge = d.verified
						? `<span style="background:#E3F5E9;color:#106B2E;padding:2px 8px;
						     border-radius:999px;font-size:11px;font-weight:600">${__("Verified")}</span>`
						: d.source === "listed" && canVerify
						? `<button class="btn btn-xs btn-default fedco-verify"
						     data-idx="${d.idx}">${__("Mark verified")}</button>`
						: "&mdash;";

					return `<tr>
						<td><b>${frappe.utils.escape_html(d.document_type || "")}</b>
							${d.reference ? `<div style="color:#6c7680;font-size:11px">${frappe.utils.escape_html(d.reference)}</div>` : ""}
						</td>
						<td style="text-align:right">${amount}</td>
						<td><a href="${d.file_url}" target="_blank" rel="noopener">${__("Open")}</a></td>
						<td>${badge}</td>
					</tr>`;
				})
				.join("");

			const dialog = new frappe.ui.Dialog({
				title: __("Supporting Documents &mdash; {0}", [data.claim]),
				size: "large",
				fields: [
					{
						fieldtype: "HTML",
						fieldname: "docs",
						options: `
							<div style="margin-bottom:10px;color:#6c7680;font-size:12px">
								${__("Claimant")}: <b>${frappe.utils.escape_html(data.employee_name || "")}</b>
								&nbsp;&middot;&nbsp; ${__("Claimed")}: <b>${format_currency(data.total, frm.doc.currency)}</b>
							</div>
							<table class="table table-bordered" style="font-size:13px">
								<thead><tr>
									<th>${__("Document")}</th>
									<th style="text-align:right;width:20%">${__("Amount")}</th>
									<th style="width:14%">${__("File")}</th>
									<th style="width:20%">${__("Status")}</th>
								</tr></thead>
								<tbody>${rows}</tbody>
							</table>`,
					},
				],
			});

			dialog.show();

			dialog.$wrapper.on("click", ".fedco-verify", function () {
				const idx = $(this).attr("data-idx");
				frappe.call({
					method: "ghana_accounting.claim_documents.mark_verified",
					args: { expense_claim: frm.doc.name, row_idx: idx, verified: 1 },
					callback: () => {
						frappe.show_alert({ message: __("Marked verified"), indicator: "green" });
						dialog.hide();
						frm.reload_doc();
					},
				});
			});
		},
	});
}
