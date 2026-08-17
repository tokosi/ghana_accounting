# Ghana Accounting for ERPNext

Ghana tax compliance for ERPNext v15/v16. A standalone app — it does not
require the Ghana Payroll app, though the two work together when both are
installed.

## What it does

| Area | Detail |
|---|---|
| Indirect tax | VAT 15% + NHIL 2.5% + GETFund 2.5%, all charged on the **same taxable value** under Act 1151 (from 1 Jan 2026) |
| Input tax | NHIL and GETFund are recoverable, so each levy has an output and an input account |
| Withholding tax | Nine resident and non-resident categories on ERPNext's native WHT engine |
| Claim Request | Two-level approval workflow on Expense Claim, employee portal included |
| Cash Advance Request | Two-level approval workflow on Employee Advance |
| Journal Voucher | Inputter / Authorizer maker-checker with segregation of duties, plus a signed voucher print layout |
| Reports | VAT Return Summary, Withholding Tax Schedule, Statutory Compliance Summary |
| Dashboard | GL-backed number cards for each statutory payable |

### The 2026 VAT change

The COVID-19 Health Recovery Levy was repealed and the levies were re-coupled
to the VAT base. Every charge row is therefore **On Net Total** — compounding
them reproduces the cascade the reform removed and overstates the tax at about
21.9% instead of 20%. Settings warns if any row compounds.

## Install

```bash
cd ~/frappe-bench
bench get-app https://github.com/YOURUSER/ghana_accounting.git
bench --site yoursite install-app ghana_accounting
bench --site yoursite migrate
bench build --app ghana_accounting
bench --site yoursite clear-cache
```

Restart web and queue processes.

## Configure

**Ghana Accounting Settings** holds everything:

1. Levy rates — the child table drives the tax templates, so a budget change is
   a configuration edit, not a deployment
2. WHT payable account
3. Workflow toggles for claims, advances and journal vouchers
4. Filing deadline days per obligation

Then **Setup → Run Accounting Setup** to create accounts, templates,
withholding categories and workflows. It returns which companies it configured
rather than failing quietly.

### Roles to assign

Nothing approves until users hold these: `Ghana Claim Approver L1`,
`Ghana Claim Approver L2`, `Ghana JV Inputter`, `Ghana JV Authorizer`.

## The Journal Voucher workflow ships disabled

Payroll Entry creates and submits its accrual journal entry programmatically.
An active workflow on Journal Entry governs document status through approval
transitions and can leave that journal stranded in Draft, which stops payroll
posting.

Enable it in Settings, then **immediately run a test payroll entry**. If the
accrual journal does not post, disable it again.

## Works with Ghana Payroll

When the Ghana Payroll app is present, the Statutory Compliance Summary picks
up PAYE, SSNIT and Provident Fund alongside VAT and WHT, and the dashboard adds
cards for them. Without it, those lines are simply omitted — the app reads
ledger accounts by name rather than depending on payroll code.

## Uninstall

```bash
bench --site yoursite uninstall-app ghana_accounting
```

Accounts, tax templates, withholding categories and posted transactions are
left in place. Deleting them would orphan general ledger entries and break
historical reporting. Only the print format, workspace and number cards are
removed.

## Notes

- Rates are correct as published for 2026 but are your tax practitioner's call,
  not the software's. Verify before filing anything.
- The nine withholding rates in particular should be checked against the
  current GRA table.

## License

MIT
