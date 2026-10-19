# Engineer / AI handoff: ship Project Olympus incrementally

## What's supplied

A Python 3.11+ package under `src/olympus_erp`, test suite, sample QuickBooks-to-NetSuite dataset and its actual build outputs, a one-page PDF, static landing prototype, internal brand architecture, outreach workflow and the source Markdown reference documents. The `olympus` umbrella command is wired in `pyproject.toml` (plus `themis`, `peitho`, `olympus-web`, `olympus-workbench` aliases; no `hermes` command because `hermes-agent` installs one). Optional PDF support uses ReportLab.

## Repeatable verification

1. Create an isolated virtual environment and install with `python -m pip install -e ".[pdf]"`.
2. Run `python -m unittest discover -s tests -v` and address failures before extension.
3. Run `olympus hermes suggest examples/acme/open_invoices.csv netsuite.open_invoice --preset quickbooks` and verify External ID maps to Invoice Number (not Customer ID).
4. Run `olympus hermes check examples/acme/hermes.toml`, expect exit 1 and `NOT READY`.
5. Run `olympus mapping show examples/acme/hermes.toml`, then `olympus hermes build examples/acme/hermes.toml -o examples/acme/out`; expect reports, clean/reject/changes files (the shipped fictional `hermes.mappings.json` is current; delete it to see the build refuse).
6. Confirm PDF is a legible single page without clipped information. Use PDF renderer on every layout modification.
7. Create a throwaway TOML copy, confirm its mappings, `olympus themis approve --signer NAME --attest`, edit the spec, verify both the approval and the mapping decisions go stale, and confirm `olympus hermes build --require-signoff` blocks.
8. Try the MCP initialize / tools/list / tools/call handshake and check outside-workspace requests fail.
9. Verify Peitho excludes unreviewed and suppressed leads; nothing is emailed.

## Highest-value next work

**A. Vendor fidelity:** field-level fixtures for 2-3 target platforms and ten anonymized real exports; exact import metadata and sandbox pass/fail results. Add automated mapping confidence tiers and require review for ambiguity.

**B. Accuracy and safety:** parsing fuzzer/property tests, accounting reconciliation by currency/book, lineage for each field transform, error grouping by root cause, high-volume streaming with bounded memory, improve localization, secure output handling and stable output schemas.

**C. Themis enterprise mode:** authenticated reviewer identity, append-only evidence, dual-review policy, specification semantic diff, server-side storage of signatures. Never substitute AI signing for a human approver.

**D. Product UX:** desktop/local web dashboard, wizard from templates to mappings and field overrides, progress indicator, error remediation suggestions, safe anonymous sample upload option only after full security review.

**E. Business validation:** one real partner pilot, record manual hours vs Hermes-assisted hours and missed failures, update estimator from observed data, then test a clearly defined paid offer.

**F. Hosted product (only after A-E):** tenant access control, DPA, encryption, deletion TTL, security controls, Stripe or another payment processor, monitoring, customer support and ownership/licensing clarity. This code is not hosted or subscribed today.

## Hard acceptance rules

- Never claim vendor certification without independent documented approval.
- Never call data 'ready' when a required dependency could not be checked; preserve UNVERIFIED status.
- Never silently infer ambiguous date order or select one of two duplicate identifiers as correct.
- Never auto-approve a mapping spec, and always invalidate an approval after modification.
- Never put sensitive values into client-facing summary PDFs by default.
- Never send a Peitho email without the responsible user's explicit informed decision and compliance checks.
- Never call timing estimates contractual fixed quotes.

## How this work relates to the three uploaded files

`references/README.md` describes the original LoadReady capabilities; `references/report.md` is an example report from an earlier separate data run. The original application's Python code and its real sample CSV files were not attached. Therefore, this is an independent source implementation with its own synthetic test dataset and its own derived numbers.
