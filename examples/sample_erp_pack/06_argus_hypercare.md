# Argus — Post-launch support and monitoring: Acme ERP Transformation Pilot
No telemetry connection exists in this package. Targets below must be agreed with the customer.

## Suggested signal catalog
- Integration failures and retries (requires instrumentation)
- New import rejects and data-quality drift
- Financial reconciliation discrepancies
- Failed workflows, permissions and login problems
- Ticket volume, response time, resolution time
- User adoption and successful critical transaction completion

## Severity playbook
- P1 — Financial or business operations materially blocked: page named human responder
- P2 — Significant degraded workflow: open accountable ticket with reproduction steps
- P3 — Noncritical usability/reporting problem: prioritize in improvement backlog

## Closure evidence
- Incident identifier and timestamps
- Customer impact and root cause
- Change approval if applicable
- Verified fix and regression test
- Customer acceptance and prevention action

Do not treat model-generated severity or root cause as verified evidence.

