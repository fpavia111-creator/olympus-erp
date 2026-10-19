# Olympus ERP

**Find import-breaking data problems, reconcile trial loads, and create the evidence pack your ERP project needs — before go-live.**

Olympus ERP is one local, open-source (MIT) workspace for ERP data migrations. It runs on your own machine. There's no cloud upload, no vendor API and no model key. It's built for NetSuite implementation consultants and mid-market finance and operations teams. It does not replace a qualified implementation partner, and it never approves a go-live on its own.

| Module | Job |
|---|---|
| **Hermes** | Read CSV/XLSX exports, suggest column mappings with confidence tiers, and run deterministic checks: required fields, formats, duplicate IDs, broken parent references, unbalanced journals. Writes clean files, rejects with original line numbers and values, and a log of every value it changed. |
| **Mapping table** (Hermes + Themis) | A person confirms or overrides each suggested mapping. Ambiguous or low-confidence rows must be decided one by one. Decisions are saved as a versioned, SHA-256-hashed file bound to the exact spec and source bytes. No import-ready file is built without them. |
| **Themis** | Mapping-spec sign-off: an explicit human approval receipt tied to the spec's SHA-256. Any edit makes it stale. |
| **Poseidon** | Compare a source export with a trial-load export by business key, row count and amount. |
| **Apollo / Clio** | UAT scenarios with step-level test steps. Clio stores manual results with an execution timestamp and an evidence file (fingerprinted) and/or link. A result goes stale when the project, the test case or the evidence changes. |
| **Chronos** | Cutover runbook, including the backup, rollback and cutover window section with named accountable owners. |
| **Zeus** | Conservative go-live gate built from file-backed evidence. It never outputs GO. Its best possible answer is "EVIDENCE COMPLETE — HUMAN GO/NO-GO DECISION REQUIRED". |
| **Argus** | Local ERP hypercare incident queue per project, with a hash-chained (tamper-evident, not tamper-proof) log. **Olympus Argus is unrelated to Kurt Francisco's separate product *Argus of MCP*** (an MCP server/skill scanner). |
| **Athena, Daedalus, Hestia, Plutus** | Rules-based planning drafts: discovery, integration design, training and ROI scenarios. Drafts are never evidence. |
| **Peitho** | Scoring and outreach drafting for leads a person has already reviewed. It never sends anything. |

## Install

Python 3.11 or newer.

```sh
python -m venv .venv && . .venv/bin/activate        # Windows: py -3 -m venv .venv; .venv\Scripts\Activate.ps1
python -m pip install -e ".[pdf]"                   # from PyPI later: pip install "olympus-erp[pdf]"
python -m unittest discover -s tests
```

The core uses only the standard library. ReportLab (the `pdf` extra) adds the PDF reports. `mcp` adds the optional official MCP SDK adapter.

## Quick start: the dashboard

```sh
olympus web --workspace . --port 8765               # or ./START_OLYMPUS_MAC_LINUX.sh / START_OLYMPUS_WINDOWS.bat
```

Open http://127.0.0.1:8765, click **Use fictional demo**, then go to **02 · Diagnose & map** and click **Use fictional demo export**.

1. **Diagnose:** Hermes previews the findings using its suggested mappings. Status is `UNVERIFIED` or `NOT READY`, never `READY`, until the mapping is confirmed.
2. **Mapping table:** every target field shows its suggestion, confidence tier and reason. Tick each row. *Accept all HIGH / MEDIUM* ticks only those rows. LOW, AMBIGUOUS and unmatched required rows have to be decided individually. Enter your name, attest, and confirm.
3. **Build import-ready files:** you get clean CSVs, rejects (source line plus original values), `*.changes.csv` (every transformed value: original → output → reason) and a report. Download them as a ZIP.
4. **Poseidon:** reconcile the source against the trial-load export.
5. **Prepare:** generate the 10-document pack. Record UAT results step by step, with when the test ran and the evidence.
6. **Project summary:** open blockers, source-file fingerprints, target load counts, exceptions and Zeus status. Download as MD, JSON or PDF.

![Mapping table](docs/DASHBOARD_MAPPING_TABLE.png)

Every web operation is loopback-only (127.0.0.1). Request tokens and Host/Origin checks limit browser misuse, **but there is no user authentication**. Don't use real customer data on a shared computer, and don't expose the port.

## Command line

```sh
olympus --help
olympus hermes suggest examples/acme/open_invoices.csv netsuite.open_invoice --preset quickbooks
olympus hermes check examples/acme/hermes.toml           # exit 1 = NOT READY (expected for the demo data)

olympus mapping show examples/acme/hermes.toml           # the mapping table with tiers
olympus mapping confirm examples/acme/hermes.toml --reviewer "Your Name" --attest --interactive
#   or: --accept-suggestions (HIGH/MEDIUM only) plus --set LOAD.FIELD=Header / --unmap LOAD.FIELD for review rows
olympus hermes build examples/acme/hermes.toml -o examples/acme/out   # refuses without current decisions

olympus themis approve examples/acme/hermes.toml --signer "Your Name" --attest
olympus hermes build examples/acme/hermes.toml -o out --require-signoff

olympus poseidon --workspace . --source examples/poseidon/source_balances.csv --target examples/poseidon/trial_balances.csv \
  --source-key "External ID" --target-key "External ID" --source-amount Amount --target-amount Amount
olympus clio --workspace . record --project projects/<id>/project.json --case-id UAT-01-1 --result PASS \
  --reviewer "Name" --executed-at 2026-10-19T14:30-05:00 --step UAT-01-1.S1=PASS --step UAT-01-1.S2=PASS \
  --step UAT-01-1.S3=PASS --evidence projects/<id>/uat_evidence/run1.pdf --attest
olympus summary projects/<id> -o projects/<id>/summary   # project_summary.md/.json/.pdf
olympus erp pack examples/erp_project.json -o my_plan    # 10 planning drafts (Chronos reads the "cutover" object)
olympus argus --workspace . list
olympus peitho draft examples/peitho_leads.csv -o drafts.md
```

`olympus-web`, `olympus-workbench`, `themis` and `peitho` are also installed as short aliases. **There is no `hermes` command**, because the popular `hermes-agent` package installs one. Use `olympus hermes …`.

Exit codes from `check`/`build`: 0 = READY, 1 = not ready, 2 = configuration or usage error. Source paths in a spec are resolved relative to the spec. XLSX formulas are rejected (paste values first), and `.xls`/`.xlsm` are unsupported.

The demo dataset is deliberately broken (bad emails, negative amounts, duplicate IDs, missing references, an unbalanced journal), so **NOT READY is the expected result**. `examples/acme/hermes.mappings.json` is a fictional demo confirmation. `examples/acme/out/` holds its build.

### Spec format (TOML)

```toml
[project]
name = "Finance modernization"
source_system = "sage"      # optional preset hints (LOW confidence until confirmed)
day_first = false

[[load]]
name = "customers"
template = "netsuite.customer"
source = "exports/customers.csv"
[load.map]                  # human-declared mappings show as HIGH in the table; still confirmed there
"External ID" = "CustomerCode"
[load.defaults]
"Country" = "US"
[load.values.Terms]
"N30" = "Net 30"
```

Templates are starting points, not vendor-approved import specifications. Custom fields go under `[load.fields.<name>]` (`type`, `required`, `enum`, `unique`). Changing the spec, a source file or a header row makes the mapping decisions and Themis approval stale.

### Project file: cutover facts

```json
"cutover": {"window_start": "2027-04-16T18:00", "window_end": "2027-04-18T06:00", "timezone": "America/Chicago",
            "backup_taken_by": "2027-04-16T17:00", "backup_method": "…", "rollback_trigger": "…", "rollback_method": "…",
            "rollback_deadline": "2027-04-17T22:00", "cutover_owner": "Full Name", "backup_owner": "Full Name",
            "rollback_owner": "Full Name", "go_no_go_approver": "Full Name", "business_signoff_owner": "Full Name"}
```

Placeholders such as "TBD" or "TO ASSIGN" count as missing.

## MCP (local stdio)

```sh
olympus mcp --workspace /path/to/project      # 26 tools, newline-delimited JSON-RPC
olympus-mcp-sdk --workspace .                 # optional official SDK v2 adapter, 15 tools (pip install -e ".[mcp]")
```

All paths are confined to the workspace. AI tools can read the mapping table, mapping status, UAT status and the project summary. They **cannot** confirm mappings, sign off a spec or record UAT results; those are human-only, through the dashboard or the CLI. `build` refuses until a human has confirmed the mappings. See `docs/MCP_INTEGRATION.md`.

## Offer and licence

The code is MIT-licensed (see `LICENSE`): the free tool plus a demo for adoption. The commercial offer is a service built on it, the **Hermes + Poseidon Migration Integrity Scan**:

- a scoped readiness review (**$499–$1,500**), and
- a trial-load assurance project (**$1,500–$5,000**).

Both are priced by scope (objects, files, rounds, environment) and need agreed data-handling terms. These are pilot hypotheses, not quoted results. See `docs/GO_TO_MARKET.md` and `docs/OLYMPUS_V04_PLATFORM_ROADMAP.md`.

## Limits

This is a local single-user tool. It is not a certified vendor connector, not hosted SaaS and has no SSO. Reviewer names are recorded but not identity-verified. It doesn't reconcile a full GL, currencies or tax, it doesn't monitor a live ERP, and estimates are not quotes. Read `docs/SECURITY_AND_LIMITS.md` before using real data.

NetSuite, Salesforce, Workday and QuickBooks are trademarks of their owners. No affiliation or certification is claimed. Public service descriptions from rhlenterprise.com are cited in the roadmap only as market context.

## More

- `docs/OLYMPUS_V04_PLATFORM_ROADMAP.md`: commercial blueprint and sprint plan
- `docs/V04_DEVELOPER_HANDOFF.md`, `docs/HANDOFF.md`: how to continue development and the verification steps
- `docs/SECURITY_AND_LIMITS.md`, `docs/MCP_INTEGRATION.md`, `docs/BRAND.md`, `docs/GO_TO_MARKET.md`
- `RELEASE_NOTES.md`: version history
- `references/`: the original LoadReady README and an older example report, kept for history
