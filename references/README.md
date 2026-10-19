> **Historical reference.** The original LoadReady README that Hermes was re-implemented from. Commands here (`loadready …`) are not installed by Olympus ERP; use `olympus hermes …`.

# LoadReady

Find and fix legacy data problems **before** an ERP, CRM or HCM go-live.

Point LoadReady at the CSV exports from the old system (QuickBooks, Sage,
spreadsheets, an old CRM), tell it which import each file becomes (NetSuite
customers, Salesforce contacts, Workday workers...), and it:

- cleans what is safe to clean automatically: dates into the target format,
  `$1,234.50` and `(500)` into numbers, `Illinois` into `IL`, `USA` into `US`,
  emails lower-cased, legacy picklist values translated (`N30` → `Net 30`);
- rejects what a human must fix, with the line number and the reason: blank
  required IDs, bad emails, two emails in one cell, unknown states, duplicate
  IDs, negative credit limits, unknown picklist values;
- checks across files: invoices pointing at customers or items that don't
  exist (or were rejected), managers who aren't in the worker file, journals
  whose debits and credits don't balance;
- flags likely duplicate records (`Brightline Fabrication LLC` vs
  `Brightline Fabrication`);
- writes clean import CSVs, a `*.rejects.csv` per file for the data owner, and
  a readiness report with an hours-and-cost estimate for the clean-up.

Pure Python 3.11+, no dependencies. Ships as a CLI, an MCP server and a
Claude Code plugin with a skill.

## Quick start

```bash
pip install -e .

loadready templates                         # what it can target
loadready profile legacy/customers.csv      # what's in an export

loadready init --name "QuickBooks to NetSuite" \
  --load netsuite.customer=legacy/customers.csv \
  --load netsuite.item=legacy/items.csv \
  --load netsuite.open_invoice=legacy/open_invoices.csv \
  --load netsuite.journal=legacy/opening_balances.csv

loadready check                              # readiness report (exit 1 if not ready)
loadready build -o out/                      # clean files, rejects, report.md/json
```

Try the bundled sample (a manufacturer moving from QuickBooks to NetSuite,
with 13 planted problems):

```bash
loadready check examples/acme/loadready.toml
```

See [examples/acme/out/report.md](examples/acme/out/report.md) for the output.

## Templates

| Template | Target |
|---|---|
| `netsuite.customer`, `netsuite.vendor`, `netsuite.item` | NetSuite master data |
| `netsuite.open_invoice` | Open AR invoices (checked against customers and items) |
| `netsuite.journal` | Opening-balance journal (balanced per journal) |
| `salesforce.account`, `salesforce.contact` | Salesforce Data Loader upserts by external ID |
| `workday.worker` | Workday hire load (map onto your tenant's EIB) |

Templates are starting points, not vendor specifications. Every account has
its own custom fields, mandatory segments and picklists, so a spec can
override any column or add new ones:

```toml
[load.fields."custentity_region"]
required = true
type = "enum"
enum = ["East", "West"]
```

## The spec

```toml
[project]
name = "Acme: QuickBooks to NetSuite"
day_first = "auto"      # or true (DD/MM) / false (MM/DD)
rate_low = 150          # $/hour for the effort estimate
rate_high = 250

[[load]]
name = "customers"
template = "netsuite.customer"
source = "legacy/customers.csv"

[load.map]                       # target column = source column
"External ID" = "Customer ID"
"Company Name" = "Customer Name"
"Address 1" = ["Street", "Suite"] # a list is joined with spaces

[load.defaults]                  # fills blanks
"Subsidiary" = "Acme Manufacturing Inc."

[load.values.Terms]              # legacy value -> target value
"N30" = "Net 30"
```

## Using it from Claude

The plugin registers the MCP server (`loadready mcp`) and a `loadready`
skill. Tools: `list_templates`, `describe_template`, `profile_file`,
`suggest_mapping`, `write_spec`, `check`, `build`. A typical session: "Here
are our QuickBooks exports, we're going to NetSuite. What will fail?"

## Tests

```bash
pip install pytest && python -m pytest -q
```

## Limits (v0.1)

- CSV only; save Excel sheets as CSV first.
- Reads files, never connects to the target system. Run the vendor's own
  import in a sandbox as the final check.
- Duplicate detection is name normalisation, not fuzzy matching across
  typos.
- The effort estimate uses fixed minutes per problem type. It's a planning
  aid, not a quote.
