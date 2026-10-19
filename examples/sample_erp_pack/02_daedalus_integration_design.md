# Daedalus — Integration design draft: Acme ERP Transformation Pilot
Draft only: vendor API permissions, schemas, limits, entity mappings, and idempotency must be verified in each tenant.

| From | To | Data / business event | Implementation pattern | Approval |
|---|---|---|---|---|
| Salesforce | NetSuite | Accounts and closed-won sales orders | Design API or approved file transfer after tenant review | Architecture owner |
| Shopify | NetSuite | Web orders and fulfillment states | Design API or approved file transfer after tenant review | Architecture owner |

## Design review checklist
- Read-only credential scopes during exploration
- Field ownership and system of record
- Identity, lookup keys, and duplicate treatment
- Retry, dead-letter, idempotency and rate limits
- Sensitive-data and encryption boundaries
- Audit logs and operational alert ownership
- Sandbox reconciliation before production permission request
- Documented rollback and error handling

