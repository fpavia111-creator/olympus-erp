# Security, privacy, reliability and known limitations

## Current protective design

- Local input/output only; no API calls, telemetry, or background processing.
- MCP workspace containment for every requested input/spec/output path (source paths in TOML checked too).
- Spreadsheet-like formula payloads in target text fields are rejected; XLSX workbook formulas require paste-as-values exports.
- Duplicate primary keys reject all conflicting records; broken references and parent rejection propagate through dependent loads.
- Ambiguous day/month strings are rejected in `day_first="auto"` rather than guessed.
- Import-ready files require a human-confirmed mapping table (versioned, hashed, bound to spec, source bytes and headers); ambiguous/low-confidence rows need explicit decisions, and every changed value is logged in `*.changes.csv`.
- Approval requires human terminal acknowledgement and is tied to a SHA-256 of the exact mapping spec bytes; edits make a receipt stale.
- Reports omit customer field values by default, but may contain identifiers embedded in diagnostic messages. CSV rejects and CSV clean outputs contain actual customer data.

## Known engineering limits

- The 11 templates are illustrative and incomplete; account-specific required fields, picklists, subsidiary restrictions and relationship conventions must be reconciled manually.
- The engine does not log into ERP/CRM/HCM platforms, perform target validation, secure tenant permissions, or verify against a live vendor API.
- XLSX reader supports common shared-string and numeric/date styles. It rejects formula cells, ignores Excel display-only formatting and charts, and does not support `.xls`, `.xlsm`, merged headers, password-protected files or workbook macros.
- Source file limit: 60 MB; unpacked XLSX limit: 25 MB total (bounds memory, because XML parts are parsed in memory). Dashboard uploads: 3 MB per file, 1.5 MB per reconciliation side. Intended for early pilots rather than large enterprises.
- Duplicate names are detected by simple punctuation/corporate-suffix cleanup, not probabilistic entity resolution.
- Address validation is US-state-centric; country dictionary only covers a small set of examples. Add locale-aware mappings for international deployments.
- Journal checks require a batch with at least one debit and one credit; current aggregate checks verify balance per Journal ID but not chart-of-accounts, currencies or posting periods.
- Effort estimates assume **2 baseline hours per load** plus fixed error weights; they are not learned from projects and are not quotes.
- `Themis` approval is not cryptographically signed with a private key, not identity-verified, and not tamper-proof against someone changing both the spec and receipt. Build integration is a workflow guard, not legal attestation.
- The MCP implementation covers the tested core stdio methods. Compatibility and permission behavior must be retested with each actual target client and security policy.
- `Peitho` does not access a CRM, send mail, discover emails, or guarantee compliance with applicable outreach law.

## Before accepting real client data

- Execute a signed scope document and review NDA / DPA obligations.
- Work in an encrypted, access-restricted folder; disable casual cloud sync for raw exports and rejects.
- Define retention and deletion timeframes and who may access the records.
- Establish backups, incident response, and audit logging appropriate to the environment.
- Pin and scan dependencies; conduct a code and penetration review of any web-hosted version.
- Perform CSV injection review downstream because recipients may open CSVs with spreadsheet software.
- Complete mapping review with the client's data owner; obtain verified approval.
- Run the real target's import in its sandbox and reconcile counts, balances and exceptions.
- Never use sample report or PDF as a guarantee of target import success.

## Safer hosted future architecture

Tenant-authenticated upload; scoped encrypted object storage; queue-isolated ephemeral workers; strict TTL deletion; report access authorization; secure audit log; secrets management; export encryption; observability without PII; per-tenant rate and size limits; role-based verified approvals; SOC2 readiness after operational evidence exists. Not included in this code.
