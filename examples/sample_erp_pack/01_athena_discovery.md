# Athena — ERP discovery and roadmap: Acme ERP Transformation Pilot
Customer: Acme Fabrication (fictional sample) | Proposed target: NetSuite | Industry: manufacturing

## Systems in scope
- QuickBooks Desktop
- Salesforce
- inventory spreadsheets

## Critical workflows
- quote-to-cash
- purchase-to-pay
- month-end close
- inventory receiving

## Discovered pain points
- Duplicate customer records
- Slow month-end close
- Inventory and finance don't reconcile

## Migration objects
- customers
- vendors
- items
- open accounts receivable
- opening GL balances

## Risks to validate
- Multiple legacy sources increase matching and reconciliation complexity
- Multi-location cutover and process harmonization need review

## Questions before agreeing to scope
- Which account-specific fields, roles, taxes, and subsidiaries must be supported?
- What are the backup, rollback, and acceptable downtime requirements?
- Which vendor sandbox or test tenant can be used for trial imports?

## Responsible roles
- Executive sponsor: TO ASSIGN
- Finance owner: TO ASSIGN
- Operations owner: TO ASSIGN
- IT administrator: TO ASSIGN
- Data owner: TO ASSIGN
- Training lead: TO ASSIGN

## Suggested phase gates
- 1. Approve requirements and data inventory
- 2. Approve mapping spec and technical design
- 3. Validate clean imports in a vendor sandbox
- 4. Complete critical-workflow UAT and reconciliation
- 5. Obtain written cutover, backup and rollback approval
- 6. Run post-launch hypercare with an accountable owner

This document is generated from customer-entered facts; it does not verify actual system configuration or regulatory compliance.

