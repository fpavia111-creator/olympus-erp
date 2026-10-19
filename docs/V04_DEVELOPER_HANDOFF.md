# Olympus ERP v0.4 — developer / AI engineer handoff

## Non-negotiable instruction

Extend this package; do **not** rewrite Hermes or claim capabilities not verified by tests. Keep every regression test passing (`python -m unittest discover -s tests`). Plan and execute each change as a small unit with tests. Do not connect a customer's production system without explicitly scoped, independently authorized credentials and documented rollback.

## Quick setup

```powershell
cd Olympus
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[pdf]"
python -m unittest discover -s tests -v
olympus web --workspace . --port 8765
```

Open `http://127.0.0.1:8765` **on the same computer**. It does not require an API key. Use `Use fictional demo` in Discover. All files, including each project's incident log, are stored below `./projects/<id>/`. To delete a project, select it and enter its exact name after clicking Delete. Deletion is not secure disk wiping.

MCP:

```powershell
olympus mcp --workspace .
```

Optional MCP SDK v2 adapter (smoke-tested with `mcp` 2.3.0):

```powershell
python -m pip install -e ".[mcp]"
olympus-mcp-sdk --workspace .
```

Run MCP Inspector compatibility tests with your target client. Do **not** expose Streamable HTTP before adding authentication, host/origin validation, audit logging and an access-control review. Prefer the official SDK for future production work: https://py.sdk.modelcontextprotocol.io/.

## Core modules

- `src/olympus_erp/dashboard.py`: loopback-only web server, static accessible tabs, intake and upload workflows, generated artifact ZIP, local deletion.
- `src/olympus_erp/reconcile.py`: Poseidon source versus target comparisons (immutable inputs, deterministic values).
- `src/olympus_erp/uat_evidence.py`: Clio local UAT evidence and freshness checks; never auto-grant go-live.
- `src/olympus_erp/incidents.py`: Argus local incident log and hash-chain verification.
- `src/olympus_erp/sdk_server.py`: optional SDK v2 adapter with 15 explicit wrappers.
- `src/olympus_erp/workbench.py`: human-invoked UAT evidence, incident, and reconciliation CLI.
- `src/olympus_erp/mcp.py`: original local stdio protocol subset with 26 tools; workspace bounds. UAT recording is intentionally not exposed to AI tools.
- `src/olympus_erp/engine.py`: Hermes rules engine; preserve original row-level details and the per-value change log.
- `src/olympus_erp/mapping.py`: confidence tiers and the versioned, hashed mapping-decision file; `build` refuses without it.
- `src/olympus_erp/project_summary.py`: blockers, fingerprints, load counts, exceptions and Zeus status (MD/JSON/PDF).
- `src/olympus_erp/main.py`: the `olympus` umbrella command.
- `src/olympus_erp/erp_agents.py`: ten draft artifacts from business-entered project input.
- `tests/test_v04.py`: new functional/security regression tests.

## Required next implementation, in priority order

1. **Durable, approved mapping screen:** show detected column matches, ambiguous choices and required missing columns. No import artifact is allowed until a human confirms mappings, defaults, source-of-truth and tenant-specific rules. Reuse `engine.suggest_mapping` and its TOML spec support.
2. **Source fingerprint + reconciliation manifest:** record file SHA-256, file rows, financial totals, reviewer decision and parent-file dependencies. Exports should include expected vs actual record-count tables.
3. **Project model:** replace local files with authenticated project/tenant identity and a database only after threat modeling and encryption design. Every record must be scoped to the real tenant.
4. **Official MCP SDK host validation:** install v2, run Inspector and at least one supported host; test tool list, call arguments/errors, stdio framing, cancellation and optional modern Streamable HTTP security. Update the 15-tool subset to 23 only after compatibility and permission tests.
5. **Vendor sandbox connectors:** Salesforce metadata first; NetSuite SuiteTalk after tenant-specific schema discovery; production writes never default-enabled.
6. **True UAT and signoff workflow:** verified user identity, evidence retention and real signatures where legally needed; do not equate local evidence upload with approval.
7. **Commercial readiness:** billing, user invites, deletion/retention controls, DPA/NDA, support obligations and accessible interface tests.

## Quality gates

- Fully deterministic financial/data validation independent of LLM text.
- Spreadsheet formula input rejected, output spreadsheet formula injection prevented.
- Exact mapping spec fingerprint invalidated on edit; UAT evidence fingerprint invalidated on change/removal.
- Host and Origin validation, private loopback binding, per-process web token, body limits, no arbitrary file access.
- No hidden vendor API calls, remote trackers or live credentials.
- Clear `NOT READY`, `UNVERIFIED`, `NO GO` outcomes where evidence is absent.
- The dashboard's origin checks are necessary but are **not authentication**; do not use with sensitive customer data in a shared or internet-facing environment.

## How to test an extension

Run `python -m unittest discover -s tests -v` after changes. Add an integration test for every new MCP operation and every new HTTP POST action. Test path traversal, stale evidence, false-ready results, invalid binary uploads, formula injection, unauthorized requests and partial migration failures. Test vendor compatibility in a real sandbox and capture independent evidence of acceptance before marketing the integration as working.
