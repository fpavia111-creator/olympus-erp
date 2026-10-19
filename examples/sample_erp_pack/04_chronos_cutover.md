# Chronos — Cutover runbook: Acme ERP Transformation Pilot
No production changes are performed by this document. Dates are planning placeholders, not vendor-confirmed windows.

| Timing | Required task | Accountable role | Status |
|---|---|---|---|
| 2027-03-25 | Confirm source freeze strategy, backups, data owner and rollback decision-maker | Data owner | NOT CONFIRMED |
| 2027-04-01 | Run migration rehearsals in sandbox, confirm record-count and value reconciliation | IT administrator | NOT CONFIRMED |
| 2027-04-05 | Resolve critical data exceptions and confirm integrations under test | Operations owner | NOT CONFIRMED |
| 2027-04-08 | Business owners execute and approve UAT; verify role-based permissions | Operations owner | NOT CONFIRMED |
| 2027-04-12 | Validate backups, recovery test, communications and rollback procedures | IT administrator | NOT CONFIRMED |
| 2027-04-14 | Obtain explicit human go/no-go sign-off; freeze agreed source changes | Executive sponsor | NOT CONFIRMED |
| 2027-04-15 | Human-led cutover: execute approved data loads, reconcile and monitor | IT administrator | NOT CONFIRMED |
| 2027-04-16 | Inspect failed transactions, tickets and critical workflows | Operations owner | NOT CONFIRMED |
| 2027-04-22 | Hypercare review and transition to managed-service ownership | Executive sponsor | NOT CONFIRMED |

## Go/no-go gate
- Approved data mapping and ownership
- Successful test import and financial reconciliation
- UAT passes with critical issues addressed
- Documented and tested rollback option
- Signed release and downtime authorization
- Named on-call support and escalation chain

**Default: NO GO until owners independently verify evidence.**

