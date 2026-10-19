# Olympus ERP 0.4.0 — Migration Integrity workspace (local, unreleased)

- **Positioning:** one Olympus workspace; lead offer is the Hermes + Poseidon Migration Integrity Scan (scoped readiness review $499–$1,500; trial-load assurance $1,500–$5,000). Free MIT-licensed tool and demo.
- **Licence:** MIT (Copyright (c) 2026 Kurt Francisco). Package `olympus-erp`, import package `olympus_erp`, umbrella CLI `olympus`. No `hermes` console script (clashes with `hermes-agent`); `loadready` alias removed.
- **Mapping table (Hermes + Themis):** confidence tiers HIGH / MEDIUM / LOW / AMBIGUOUS / NONE in the dashboard and `olympus mapping show|confirm`; every field needs a human decision; LOW/AMBIGUOUS/unmatched-required rows need an explicit per-row decision; bulk accept limited to HIGH/MEDIUM; overrides and unmapping supported. Decisions stored in `<spec>.mappings.json` (versioned, self-hashed, previous-hash chain, history folder) bound to spec, source-file and header hashes. `build` refuses to write import-ready files without current decisions; `check` reports UNVERIFIED.
- **No silent mutation:** rejects carry original source values (`source:<column>`) and line numbers; `<load>.changes.csv` logs every transformed value with reason.
- **Apollo/Clio:** step-level test steps; manual results need executed-at time, evidence file (fingerprinted) and/or link, per-step results consistent with the case outcome; results go stale when project facts, the test case/steps or evidence change.
- **Project summary:** open blockers by area, source-file fingerprints, latest build load counts and exception codes, reconciliation, UAT, cutover, incidents and Zeus status — dashboard tab, `olympus summary`, MD/JSON/PDF, MCP `project_summary`.
- **Chronos:** backup / rollback / cutover-window section with named accountable owners (dashboard fields and project JSON); placeholders count as missing.
- **Zeus:** never outputs GO; best result is "EVIDENCE COMPLETE — HUMAN GO/NO-GO DECISION REQUIRED", only from file-collected evidence; model assertions or draft flags in project input are ignored and listed.
- **Fixes:** XLSX uncompressed limit lowered to 25 MB; dashboard incidents are project-scoped and deleted with the project; MCP tool count text corrected (26); sample domains use example.com; author metadata added; private business analysis moved out of the release tree.
- Tests: 68 passing on Python 3.11, 3.12 and 3.13.

# Unreleased (release-readiness pass, 2026-10-19)

- MCP stdio server: malformed JSON no longer answers with a previous request's id; non-object/batch requests no longer crash the server; correct JSON-RPC codes (-32700/-32600/-32601/-32602); tool arguments validated against the advertised inputSchema; tool failures returned as `isError` results per the MCP spec; protocol version negotiated.
- Argus incident log: appends serialized so concurrent dashboard requests cannot fork the hash chain (which previously made the whole log unreadable).
- Dashboard: constant-time token comparison; friendly error when the port is in use.
- Peitho: `source_url` / `source_note` sanitized like company/contact in drafts.
- SDK adapter: workspace-boundary and validation errors are shown to the model instead of a generic failure.
- Launchers: accept any Python 3.11+ (Windows previously required exactly 3.11), install the `pdf` extra, `OLYMPUS_PORT` override on Mac/Linux.
- 9 regression tests added (45 total).

# Olympus ERP v0.4 — Local Workbench (2026-10-19)

- Four-stage live local dashboard at `olympus-web --workspace . --port 8765` (Discover, Diagnose, Prepare, Operate).
- Browser-guided project setup, CSV/XLSX diagnosis, sample mapping/readiness findings, and ten-document ZIP download.
- Poseidon deterministic source/trial-load key, row-count and amount reconciliation. A discrepancy is never silently normalized.
- Clio UAT records with checksums of evidence and project: stale or missing proof invalidates PASS display.
- Argus manually-entered incident queue and hash-linked local history; this is tamper-evident only, not a secure audit database.
- Local project switching and explicit deletion; per-process request token, Host/Origin restrictions, CSP, size limits and localhost-only binding.
- 23 legacy-subset MCP tools (five additional in this version). UAT recording intentionally **not** exposed through MCP; human CLI/UI only.
- Optional official MCP Python SDK v2 adapter declares 15 tools; external package unavailable during these tests, not yet compatibility-verified.
- 36 regression tests passing, including backend HTTP host/token/origin tests. Live browser interaction was not confirmed in this environment; static visual layout was rendered.
- New source/test files: `dashboard.py`, `reconcile.py`, `uat_evidence.py`, `incidents.py`, `workbench.py`, `sdk_server.py`, `tests/test_v04.py`.
- Open limitations: no NetSuite/Salesforce/Workday API credentials, no real-time monitoring, no verified reviewer identity, no hosted auth, no live vendor trial-import certification.

---

# v0.3.0 — ERP consulting extension (2026-10-19)

- Reviewed publicly described ERP consulting services (cited public pages only) and mapped product opportunities; the internal analysis is kept outside the release tree.
- Added local deterministic Greek-mythology-named document agents: Athena, Daedalus, Apollo, Chronos, Hestia, Argus, Plutus, Zeus.
- Added **10** MCP tools to the existing **8**; preserved original Hermes server identity for compatibility with v0.2.
- Added `olympus-erp` CLI with `assess` and `pack`; generates a 10-file draft consultant packet for a fictional manufacturer, never overwrites a pack folder.
- Added 8 new unit tests, for **27 passing** including the original 19.
- No live vendor connectors, independently certified ERP mappings, compliance promises, email sending, or production deployment.

# Project Olympus prototype - delivery notes

Release: 0.2.0 (local prototype)

Components:
- Hermes: 11 migration templates, CSV/XLSX input, field validation, parent relationships, balanced journals, clean files, rejects, full reports, PDF and local MCP.
- Themis (mapping-spec sign-off): SHA-256 spec approval receipts with stale-on-change gate, explicitly human-controlled.
- Peitho: local reviewed lead qualification and outreach drafts, no email sending.
- Olympus: umbrella brand, responsive Hermes landing prototype, original document references, developer handoff and GTM plan.

Verification: `python -m unittest discover -s tests -v` -> 19 tests passed.

Sample output: synthetic demo has 22 rows, 11 loadable (50%), 14 errors, 1 warning. The estimate is heuristic and not a customer quote. The generated PDF has 1 US Letter page and was visually inspected after rendering.

These modules are independent implementations written from three uploaded Markdown documents, not modifications of earlier repositories. No production environment, live ERP account, lead databases, connected mail service, or live checkout was configured. Vendor validation, trademark clearance, business pilot and identity-backed approval remain future work.
