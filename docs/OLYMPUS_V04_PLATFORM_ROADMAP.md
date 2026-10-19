# Olympus ERP v0.4 — platform development and commercial blueprint

## Executive decision

Build **one Olympus ERP workspace** with Greek agent modules; do not build 26 disconnected bots. Begin by selling the **Hermes + Poseidon Migration Integrity Scan** to NetSuite implementation consultants and mid-market teams. Connect the diagnostic service to the Athena → Apollo → Clio → Themis → Chronos workflow when real pilots justify expanding.

**Positioning:** "Find import-breaking data problems, reconcile trial loads, and create the evidence pack your ERP project needs—before go-live." Do not claim a complete ERP implementation, security certification, or guaranteed cost reduction.

RHL Enterprise's published services include ERP advisory, data migration/integrations, system design and testing, UAT/compliance support, cutover, training, hypercare, stabilization, and KPI/SLA reporting. Its site is a public description of those services, not evidence of RHL's proprietary methods or its project pricing. Sources: https://www.rhlenterprise.com/services, https://www.rhlenterprise.com/deployment-services, https://www.rhlenterprise.com/post-deployment-services.

## How a customer experiences Olympus

| Stage | User accomplishes | Current v0.4 implementation | Human accountability |
|---|---|---|---|
| 01 Discover | Describe target ERP, sources, workflows and pain points | Local forms save `project.json`; Athena highlights missing inputs | Confirm scope, roles and requirements |
| 02 Diagnose | Upload and analyze source exports | Hermes reads CSV/XLSX, suggests mappings, checks data; Poseidon compares paired source/trial-load files | Confirm account-specific mapping, source-of-truth and trial-import reconciliation |
| 03 Prepare | Produce a migration/test/cutover packet | Generates ten draft documents; Clio records self-attested UAT result + checks evidence hash changes | Actually execute UAT and sign off; production go-live is never auto-authorized |
| 04 Operate | Record manual issues and status | Argus local incident queue with hash-chained change log | Operations owner handles triage, escalation and SLA |

The dashboard is intentionally `127.0.0.1` only with same-origin and per-process request-token checks, input limits, and no CDN. These are demo controls, not enterprise authentication or tenant isolation. Project removal deletes its application folder but is not secure erasure of disk copies/backups.

## Technical modules (real functionality versus prototypes)

- **Hermes:** 11 illustrative target templates, CSV/XLSX reading, field mapping, deterministic validation and local reject/clean files.
- **Poseidon:** deterministic numeric reconciliation by user-supplied business key and amount field. Compares counts and totals, flags missing keys, excludes and reports invalid rows. It does *not* reconcile full GL, currencies, tax, subledger, or any live ERP.
- **Clio:** UAT scenario register + human-entered PASS/FAIL/BLOCKED + fingerprinted local evidence. If a project or evidence file changes, previously recorded proof is marked stale. No verified identity or independently validated UAT results.
- **Themis:** mapping spec approval hash and explicit CLI attestation; no automated approval-authoring tool.
- **Argus:** manually entered local tickets, status changes, and hash chain tamper detection (not secure against a local adversary who can rewrite the entire file).
- **Athena, Daedalus, Apollo, Chronos, Hestia, Plutus:** rules-based planning and scenario generators. Their output is a draft and may omit necessary vendor/tenant-specific items.
- **Zeus:** `NO GO — NOT VERIFIED` until independently confirmed release evidence; software never unilaterally approves go-live.
- **Peitho:** lead scoring and outreach drafting only, with human review and no sending.

The **legacy stdio JSON-RPC MCP subset exposes 23 tools** after five new v0.4 tool additions. The separate optional **official SDK v2** adapter declares 15 frequently useful tools but has *not been tested against the external SDK* in this build environment. Run an MCP Inspector compatibility test before adopting it for customers. Details: https://py.sdk.modelcontextprotocol.io/.

## What buyers can purchase first (hypotheses)

1. **Free teaser:** demo with artificial source data; explain what errors the tool can catch, but no public upload of real confidential exports.
2. **$499–$1,500 scoped readiness review:** a limited number of export files, row-level problems, a sample correction backlog, and a fixed deliverable. Manual security and data-sharing agreements required.
3. **$1,500–$5,000 trial-load assurance project:** readiness scan + reconciled data sample + UAT execution checklist and a human-reviewed cutover packet. Price by scope, objects and environment, not pretend-unlimited usage.
4. **$199–$999/month consultant workspace pilot:** only after a professional UI, actual tenant isolation, data lifecycle controls, billing and support are completed.

No prices above are quoted from RHL and no savings or conversions have been demonstrated. Use them as interviews/pilot experiments.

## Recommended build sequence

### Sprint 1 — first customer-quality migration result

- Recruit three implementation partners with *approved synthetic or non-sensitive trial exports*; document output accuracy independently.
- Capture raw counts and amount totals, ERP import rejects, reviewed mapping decisions and confidence/exception reasons.
- Add account-specific versioned NetSuite templates validated against a real sandbox export/import, tracking ERP version, tenant configuration and approval provenance.
- Replace file preview's implicit mapping guesses with an interactive, confirmable mapping table before creating import-ready artifacts.

**Acceptance:** zero unmapped-required-field false positives passed as READY; all rejection line numbers trace to originals; no silent data mutation; successful customer trial-import after signoff, confirmed by the customer.

### Sprint 2 — implement evidence-driven cutover planning

- Extend Apollo with scenario-level test steps and manual result entry including timestamp and independent evidence link.
- Add named real approver identity through SSO and a permissioned approval ledger; a plain signer name is insufficient.
- Produce a project summary with open blocker counts, source-file fingerprints, target load counts and exceptions.
- Formalize backup, rollback and cutover time windows, tied to accountable business owners.

**Acceptance:** a stale spec or evidence file always forces review. No go-live recommendation can be generated from a draft or a model's assertion alone.

### Sprint 3 — optional, authenticated sandbox connections

- Begin with a **Salesforce sandbox read-only metadata** connector, then narrowly scoped sandbox write tests using explicit idempotency and rollback controls.
- Add NetSuite SuiteTalk REST connector only after role permissions, tenant-specific schema, mappings, API limits and token handling are reviewed.
- Do not add Workday HCM ingestion until employee-data protection and legal obligations have been assessed.

**Acceptance:** read-only by default; complete request/response provenance (with secrets redacted); replay-safe upserts; negative permissions tests; per-tenant isolation and rate-limit handling. Manual approval for any mutation, two-person approval for high-impact production bulk changes.

### Sprint 4 — honest managed-services value

- Customer-defined metric thresholds for inventory errors, stale syncs, queue lengths, trial-balance variances and UAT defects.
- Authenticated incident ticketing and escalation; tested time zones, outage handling and notification channels.
- Measured pilot outcomes: baseline hours per record object, defect rate, trial imports rejected, elapsed hours and analyst hours after tool use.

**Acceptance:** results from actual pilot data, not marketing estimates or LLM output. No uptime/SLA claim without real instrumentation.

## Unavoidable product/security work before selling SaaS

SSO/RBAC, per-tenant data isolation, upload malware controls, encryption, secrets management, cloud tenancy architecture, consent/retention and deletion policy, backups/restores, customer terms, audit identity verification, privileged-access review, threat model, independent security testing, application telemetry and operational support. Never expose the provided development dashboard as a customer-facing internet service.

## Metrics for the first 5 pilots

| Metric | Capture | What would count as evidence |
|---|---|---|
| Mapping time | Human start/end timestamps | Time spent before vs after with comparable objects |
| Validation quality | Independently sampled rows | Confirmed true positive / false positive / false negative rates |
| Trial import success | Vendor sandbox result and logs | Records accepted/rejected with reasons and timestamp |
| Reconciliation confidence | File fingerprints and totals | Matched key/count/amount plus reviewer confirmation |
| Customer value | Agreed pilot scorecard | Verified budget/time savings and deployment quality, not an estimate |

## Explicit non-goals for v0.4

No unattended email sending; no full ERP replacement; no automatic vendor API integration; no automatic production system configuration; no independent legal/compliance advice; no financial-transaction authorization; no guarantee that these sample templates satisfy a customer's ERP tenant.
