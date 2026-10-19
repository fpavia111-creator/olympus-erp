# Data migration readiness: Acme Manufacturing: QuickBooks to NetSuite

**NOT READY**: 26 of 41 rows (63.4%) pass every check.

Estimated clean-up and load effort: **9.6 hours** ($1,440 to $2,400 at $150 to $250/hour).

| Load | Target | Rows | Loadable | Rejected | Warnings |
|---|---|---:|---:|---:|---:|
| customers | netsuite.customer | 14 | 8 | 6 | 1 |
| items | netsuite.item | 9 | 7 | 2 | 0 |
| open_invoices | netsuite.open_invoice | 10 | 6 | 4 | 0 |
| opening_balances | netsuite.journal | 8 | 5 | 3 | 0 |

## customers (NetSuite Customers)

Source: `customers.csv`

Fixed automatically: 14 blanks filled from defaults, 12 countries converted to ISO codes, 10 legacy values translated, 3 amounts cleaned ($, commas, brackets), 3 states converted to codes, 1 emails lower-cased.

| Severity | Problem | Column | Rows | Examples |
|---|---|---|---:|---|
| error | Not a valid email address | Email | 1 | line 6 `cascade@pumps` |
| error | Required value is blank | External ID | 1 | line 7 |
| error | Number is below the allowed minimum (often a negative that should be positive) | Credit Limit | 1 | line 8 `(2,500.00)` (-2500 is below 0) |
| error | More than one email address in one cell | Email | 1 | line 9 `ap@fulton.example.com; ar@fulton.example.com` |
| error | US state not recognised | State | 1 | line 13 `Texs` |
| error | Same identifier appears on more than one row | External ID | 1 | line 10 `C1003` (Same External ID as line 4) |
| warning | Looks like the same record as another row | Company Name | 1 | line 5 `Brightline Fabrication` (Looks like line 2 (Company Name)) |

Values that need a mapping (add under `[load.values."<Column>"]`): `Texs` ×1

## items (NetSuite Items)

Source: `items.csv`

Fixed automatically: 9 amounts cleaned ($, commas, brackets), 6 legacy values translated.

| Severity | Problem | Column | Rows | Examples |
|---|---|---|---:|---|
| error | Not a number | Base Price | 1 | line 9 `N/A` |
| error | Same identifier appears on more than one row | External ID | 1 | line 10 `BRK-100` (Same External ID as line 2) |

## open_invoices (NetSuite Open AR invoices)

Source: `open_invoices.csv`

Fixed automatically: 8 amounts cleaned ($, commas, brackets), 3 dates reformatted.

| Severity | Problem | Column | Rows | Examples |
|---|---|---|---:|---|
| error | Not a recognisable date | Date | 1 | line 10 `TBD` |
| error | Required value is blank | Customer | 1 | line 11 |
| error | Points at a record that does not exist in the parent file | Customer | 1 | line 5 `C1099` (no customers row has External ID = C1099) |
| error | Parent record is rejected; fixing the parent fixes this row | Customer | 1 | line 6 `C1007` (customers row with this External ID is rejected) |
| error | Parent record is rejected; fixing the parent fixes this row | Item | 1 | line 10 `CAL-SVC` (items row with this External ID is rejected) |

## opening_balances (NetSuite Opening balance journal)

Source: `opening_balances.csv`

Fixed automatically: 8 amounts cleaned ($, commas, brackets), 8 blanks filled from defaults.

| Severity | Problem | Column | Rows | Examples |
|---|---|---|---:|---|
| error | Journal debits and credits do not balance | Journal ID | 3 | line 7 `OB-2` (Journal OB-2 is off by 93,000.00); line 8 `OB-2` (Journal OB-2 is off by 93,000.00); line 9 `OB-2` (Journal OB-2 is off by 93,000.00) |
| error | Negative amount in a Debit or Credit column; move it to the other column | Credit | 1 | line 8 `-46500` |

## Effort estimate

8.0 hours baseline (4 loads × mapping review, trial import, reconciliation) plus 1.6 hours of data clean-up:

| Load | Problem | Count | Hours |
|---|---|---:|---:|
| customers | Not a valid email address | 1 rows | 0.1 |
| customers | Number is below the allowed minimum (often a negative that should be positive) | 1 rows | 0.0 |
| customers | Same identifier appears on more than one row | 1 rows | 0.1 |
| customers | Required value is blank | 1 rows | 0.1 |
| customers | More than one email address in one cell | 1 rows | 0.0 |
| customers | Looks like the same record as another row | 1 rows | 0.1 |
| customers | US state not recognised | 1 distinct values | 0.2 |
| items | Not a number | 1 rows | 0.0 |
| items | Same identifier appears on more than one row | 1 rows | 0.1 |
| open_invoices | Not a recognisable date | 1 rows | 0.0 |
| open_invoices | Required value is blank | 1 rows | 0.1 |
| open_invoices | Points at a record that does not exist in the parent file | 1 rows | 0.1 |
| opening_balances | Negative amount in a Debit or Credit column; move it to the other column | 1 rows | 0.1 |
| opening_balances | Journal debits and credits do not balance | 1 journals | 0.8 |

_Estimates use fixed minutes per problem and are a planning aid, not a quote. Target templates are starting points: confirm required fields against your own account's import tool._
