# Olympus ERP — simple commercial MCP architecture and engineer handoff

## The product in one sentence

"Upload your legacy exports and complete a business questionnaire. Olympus produces a traceable ERP migration assessment, implementation/QA plan and ready-for-review import artifacts, then helps the team execute in a sandbox with explicit approvals."

**One MCP server, one project workspace, one dashboard, modular specialist agents.** Do not create 26 separate app servers.

## Four customer-facing screens

1. **Discover** — intake questionnaire: industry, current systems, target, key workflows, business owners, locations, data sensitivity, budget and timeline. Athena returns gaps; Plutus offers assumptions-based ROI.
2. **Diagnose** — upload permitted CSV/XLSX exports, profile data locally, suggest mappings, show row-level and cross-file errors; Hermes exports rejects and a paid-style PDF readiness report.
3. **Prepare** — approved mapping and target trial-load templates; Apollo tests, Daedalus integration draft, Hestia training, Chronos go-live plan, Themis human review.
4. **Operate** — post-launch ticket triage, reconciliations, health metrics and an improvement backlog when authenticated read-only connectors and customer approvals exist.

## Architecture

```text
Customer browser / desktop AI client
              |
       MCP client or web UI
              |
      Olympus ERP MCP SERVER (stdio local MVP; HTTPS later)
              |
       Permission-checking orchestration
              |
  +-----------+-----------+------------+-------------+
  | Hermes    | Athena    | Apollo     | Chronos      |
  | migration | discovery | tests      | cutover      |
  +-----------+-----------+------------+-------------+
  | Themis    | Daedalus  | Hestia     | Argus/Plutus |
  | signoff   | blueprint | training   | support/ROI  |
  +-----------+-----------+------------+-------------+
              |
      Scoped, access-controlled project workspace
              |
       Customer-owned source documents / test exports
              |
       FUTURE optional vendor sandbox connectors
       (read-only -> approved sandbox write -> controlled prod)
```

- **Prototype runtime**: Python 3.11+, standard-library business rules, local files; optional ReportLab to produce PDFs. The existing MCP server is a minimal line-oriented JSON-RPC stdio subset, not certified for every modern MCP host; use and test the official SDK before hosted/enterprise production.
- **Production extension**: official MCP Python SDK, authenticated Streamable HTTP, database isolation, object storage with retention controls, per-user/per-tenant scoping, secrets manager, queued worker jobs and audit logs. Do not expose local demo stdio server on a network socket.
- **No LLM dependency in core validation**: an LLM may propose mappings or summarize findings, but deterministic validators and human-verified source data decide pass/fail. Never allow model output to create synthetic approval or success evidence.

## Currently exposed MCP tools

Existing local Hermes tools: `list_templates`, `describe_template`, `profile_file`, `suggest_mapping`, `write_spec`, `check`, `build`, `signoff_status`.

New local ERP consultant toolkit:

| Tool | Required input | Output | Side effect |
|---|---|---|---|
| `assess_project` | `project` path | JSON missing fields / risk flags | None |
| `draft_erp_roadmap` | `project` | Markdown discovery and RACI draft | None |
| `draft_integration_design` | `project` | Markdown draft integration architecture | None |
| `draft_uat` | `project` | Markdown and structured test cases | None |
| `draft_cutover` | `project` | Markdown dependency/gate runbook | None |
| `draft_training` | `project` | Markdown curriculum plan | None |
| `draft_hypercare` | `project` | Markdown support playbook | None |
| `model_roi` | `project` | Scenario calculations or missing-input report | None |
| `go_live_gate` | `project` | NO GO until external signed evidence exists | None |
| `generate_erp_pack` | `project`, `output` | 10 local docs/JSON files | Writes only inside workspace to a new directory |

There are **18 tools in total**, including 8 existing migration/signoff tools and 10 new ERP advisory/QA tools. This is a tool menu, not 18 fully autonomous AI agents.

## Input contract (`examples/erp_project.json`)

Minimum: `project_name`, `company_name`, `target_system`. Optional: `industry`, `source_systems[]`, `workflows[]`, `data_objects[]`, `pain_points[]`, `go_live_date` (ISO date), `users`, `locations`, `owners`, `controls`, `integrations[{from,to,data}]`, `financial` fields. Missing discovery data is shown as MISSING/TO ASSIGN rather than filled in imaginatively.

Workflow example: a manufacturer migrates from QuickBooks and spreadsheets to NetSuite. Athena maps discovery gaps, Hermes inspects vendor-approved export files, Themis captures human mapping approval, Apollo drafts quote-to-cash UAT, Chronos drafts a cutover schedule, and Argus drafts hypercare escalation. No part of this tool can currently log into or configure a NetSuite tenant.

## Local run

Install from the project directory:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[pdf]"
python -m unittest discover -s tests -q
olympus erp assess examples/erp_project.json
olympus erp pack examples/erp_project.json -o examples/my_first_plan
olympus mcp --workspace .
```

`olympus erp pack` refuses to overwrite an existing directory; use a fresh folder each run. The ZIP includes a sample output directory already generated, so choose a different folder name.

## Stages to commercial readiness

### Stage 0: prove an honest wedge

- Keep file processing local, document consent and retention, source provenance, rejects, and read-only evidence.
- Run 3–5 **paid or closely observed** pilots; compare detected issues, billed/elapsed cleanup time, load rejects and customer satisfaction to the previous method. Numbers are proposed test goals, not existing traction.
- Add specific NetSuite customer/item/AR/AP and QuickBooks/Sage presets only when validated in real client sandboxes, with named versioned template provenance.

### Stage 1: paid product

- Add secure, authenticated UI; verified file type/size controls, threat model, and export approvals.
- Vendor-compatible mapping and reconciliation logic validated by trial import; human business-owner approvals.
- Signed-off UAT evidence (actual results) and accurate cost/scope proposals.
- Customer support terms, limitations, accessibility and disaster recovery.

### Stage 2: integrations

- Start with **Salesforce read-only metadata/schema** plus demo tenant; sandbox Bulk API upserts with explicit scopes and idempotency. Never treat test success as production approval.
- Add **NetSuite SuiteTalk REST** after tenant-specific field and role discovery. Ensure OAuth/permission strategy meets current vendor requirements.
- Add **Workday last**, because tenant-specific HCM EIBs and employee data increase implementation and privacy complexity.
- Require approval on any write; require two-person authorization for production bulk operations; allow export-only use.

### Stage 3: recurring support

- Read-only events + dashboards for Argus and Helios; normalized incident tickets and timestamped SLAs. Alert thresholds must be set by the customer.
- Versioned release-impact scanner and provenance-backed generated answers from client-approved docs.
- Auditable customer-specific ROI report based on **measured** before/after metrics.

## Security / accuracy release gates

- Per-tenant isolation and least-privilege access; encryption, secure secrets, backup/restore, retention and contractual data handling.
- Protected handling for financial, salary, health and customer data. Never put sensitive CSV contents in ordinary model prompts without explicit customer authorization and suitable controls.
- Reject workbook formulas not converted to values, spreadsheet injection, ambiguous dates, duplicate IDs and unbalanced journals when appropriate.
- Vendor API retry/rate-limit handling, idempotency keys, tenant-specific schema versioning, staging permissions and explicit rollback.
- Data mapping approvals and go-live releases must come from authorized humans. Local plaintext Themis receipts are not enterprise identity verification.
- Validate generated documents with domain experts. All model output is provisional until independently checked.

## Revenue model to test (hypotheses, not RHL prices)

- **Free lead magnet**: limited demo CSV profile with no customer data retained.
- **$499–$1,500**: fixed-scope local migration readiness assessment, subject to file/object limits.
- **$1,500–$5,000**: human-reviewed readiness plus mapping, UAT draft and implementation plan, depending on volume.
- **$199–$999/month**: software-only partner workspace based on seats/scans; enterprise onboarding separately quoted.
- **Managed support**: custom recurring contract after monitoring/connectors pass privacy and SLA validation.

Do not advertise "fully replaces RHL" or guarantee percent cost reductions before pilot benchmarks. Sell **a specific tested deliverable**, then add higher-risk automation gradually.

## Prompt for another AI engineer

> Extend the supplied Olympus v0.3 ZIP, do not rewrite Hermes from scratch. Preserve all 27 existing tests and add failing tests before any change. Implement the secure four-step web flow (Discover, Diagnose, Prepare, Operate) while keeping existing offline file functionality. Never make production ERP writes or claim certified vendor mappings. Use the roadmap in `docs/OLYMPUS_V04_PLATFORM_ROADMAP.md` as the prioritization brief and `docs/OLYMPUS_ERP_MCP_BUILD_PLAN.md` as the functional spec. Finish Stage 0 and the security foundations of Stage 1 first. Include an evidence-backed migration report, explicit customer ownership, sign-off receipts, integration sandbox tests, and accessible UI. Use the official MCP SDK for production; test host compatibility. Document exactly what is implemented vs drafted and supply a reproducible test report.
