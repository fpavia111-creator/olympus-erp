# Hermes readiness: Acme demo: QuickBooks to NetSuite (synthetic data)

**NOT READY** | 11/22 loadable rows (50.0%).
**Issues:** 14 errors; 1 warnings.
**Planning estimate:** 15.68 hours; $2,352-$3,920.

| Load | Target | Rows | Loadable | Rejected | Warnings |
|---|---|---:|---:|---:|---:|
| customers | netsuite.customer | 5 | 3 | 2 | 1 |
| items | netsuite.item | 4 | 1 | 3 | 0 |
| vendors | netsuite.vendor | 1 | 1 | 0 | 0 |
| invoices | netsuite.open_invoice | 4 | 2 | 2 | 0 |
| ap_bills | netsuite.open_ap_bill | 2 | 1 | 1 | 0 |
| inventory | netsuite.inventory_on_hand | 2 | 1 | 1 | 0 |
| journals | netsuite.journal | 4 | 2 | 2 | 0 |

## Mapping decisions

Confirmed v1 by Demo reviewer (fictional sample) at 2026-10-19T13:50:29.473427+00:00 (sha256 `14e67f8280e396a4…`).

## customers
Source: `customers.csv` (sha256 `80a90e635b4997d2…`); 16 logged value transformations

| Severity | Line | Column | Issue |
|---|---:|---|---|
| error | 3 | Email | Invalid email address |
| error | 4 | State | Unknown US state; provide a mapping |
| error | 4 | Credit Limit | Below minimum 0 |
| warning | 5 | Company Name | Possible duplicate of line 2 |

## items
Source: `items.csv` (sha256 `91d4e616e93b65b2…`); 1 logged value transformations

| Severity | Line | Column | Issue |
|---|---:|---|---|
| error | 2 | External ID | Same identifier as line 4 |
| error | 3 | Base Price | Not a valid number |
| error | 4 | External ID | Same identifier as line 2 |

## vendors
Source: `vendors.csv` (sha256 `68613dc5f5197182…`); 0 logged value transformations

| Severity | Line | Column | Issue |
|---|---:|---|---|
| - | - | - | No issues found |

## invoices
Source: `open_invoices.csv` (sha256 `ee11381cfad96f1e…`); 0 logged value transformations

| Severity | Line | Column | Issue |
|---|---:|---|---|
| error | 3 | Customer | Parent identifier absent |
| error | 4 | Date | Unrecognized date |
| error | 4 | Customer | Referenced parent record is rejected |
| error | 4 | Item | Referenced parent record is rejected |

## ap_bills
Source: `open_ap_bills.csv` (sha256 `f15ae7fcd01aa682…`); 0 logged value transformations

| Severity | Line | Column | Issue |
|---|---:|---|---|
| error | 3 | Vendor | Parent identifier absent |

## inventory
Source: `inventory.csv` (sha256 `fd1923b94f565652…`); 0 logged value transformations

| Severity | Line | Column | Issue |
|---|---:|---|---|
| error | 3 | Item | Parent identifier absent |

## journals
Source: `opening_balances.csv` (sha256 `79484bc589504f7e…`); 0 logged value transformations

| Severity | Line | Column | Issue |
|---|---:|---|---|
| error | 4 | Journal ID | Journal OB-2 out of balance by 100 |
| error | 5 | Journal ID | Journal OB-2 out of balance by 100 |

## Important limitations

- This is a local diagnostic, not a vendor-certified import or completed trial load.
- Reconcile with the real target system in a sandbox; validate custom fields and current picklists.
- Dates with ambiguous US/EU day ordering are rejected unless configured.
- Readiness excludes target-account permissions, API quotas, transformation scripts, and go-live cutover tasks.
- Estimates use fixed issue weights, not measured implementation hours.
