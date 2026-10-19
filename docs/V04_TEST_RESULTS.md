# Olympus ERP v0.4 — reproducible local validation

Run on the original build environment (Python 3.13; package supports Python 3.11+):

```sh
python -m unittest discover -s tests -v
python -m compileall -q src/olympus_erp
node --check <extracted dashboard JavaScript>
```

**36 automated tests passed.** They cover the 27 baseline tests and nine added v0.4 tests: source/target amount and count differences; missing/invalid records; stale UAT and evidence files; tampered incident history; local MCP inventory/path restrictions; web project file scans/plans; browser input reconciliation and UAT recording through the Python backend; explicit project deletion; web Host/Origin/request token restrictions.

The Python package was installed using editable mode and the `olympus-web` and `olympus-workbench` entrypoints were invoked with `--help` successfully. The rendered dashboard HTML was previewed in headless Chromium and its JavaScript syntax checked with Node. Direct end-to-end browser access to the local loopback server was blocked by administrator policy in the build environment; thus the UI's click-through journey could **not** be fully verified in the browser, even though the Python HTTP API and action handlers passed tests.

**Update 2026-10-19:** 45 tests pass on Python 3.11/3.12/3.13; `olympus-mcp-sdk` was smoke-tested with `mcp` 2.3.0 (initialize, tools/list with 15 tools, tools/call, workspace-boundary error); the dashboard's demo flow (demo project, diagnose upload, reconcile, pack ZIP download, UAT record, incident, delete) was clicked through in headless Chrome with the CSP enforced. It is still not a certified MCP host integration.

**Update 2026-10-19 (0.4.0 workspace):** 68 tests pass on Python 3.11/3.12/3.13, including 23 in `tests/test_sprint12.py` (mapping tiers and confirmation, decision versioning/staleness, no silent mutation, CLI/interactive confirm, MCP cannot confirm, Clio steps/staleness, Chronos validation, Zeus never GO, project summary formats, XLSX bomb limit, release-tree hygiene). The mapping table and project summary were clicked through in headless Chrome; screenshots: `docs/DASHBOARD_MAPPING_TABLE.png`, `docs/DASHBOARD_MAPPING_CONFIRMED.png`, `docs/DASHBOARD_PROJECT_SUMMARY.png`.

Original note: the official `mcp>=2,<3` SDK was not available from the runtime's package index at build time. The 23-tool original local JSON-RPC stdio subset remains tested at the protocol handshake level. No actual NetSuite, Salesforce, Workday, RHL or production customer-system connection was attempted.

All example data is fictional. The sample Poseidon reconciliation intentionally fails with 3 differing identifiers and a -$15.00 net amount variance; this is an expected detection result, not a software error. Any generated ERP implementation advice is a draft and must be verified by a qualified domain expert.
