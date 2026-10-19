# Apollo — User acceptance testing: Acme ERP Transformation Pilot
Test cases are drafts. Run them against a test tenant and retain independent evidence.

| Case | Workflow | Scenario | Expected evidence | Status |
|---|---|---|---|---|
| UAT-01-1 | quote-to-cash | happy path | Business owner confirms expected state transitions and ledger/data effects | NOT RUN |
| UAT-01-2 | quote-to-cash | invalid/missing input | System rejects or correctly routes invalid data without silent corruption | NOT RUN |
| UAT-01-3 | quote-to-cash | roles and exception handling | Authorized roles complete task; unauthorized access blocked; failures can be resolved | NOT RUN |
| UAT-02-1 | purchase-to-pay | happy path | Business owner confirms expected state transitions and ledger/data effects | NOT RUN |
| UAT-02-2 | purchase-to-pay | invalid/missing input | System rejects or correctly routes invalid data without silent corruption | NOT RUN |
| UAT-02-3 | purchase-to-pay | roles and exception handling | Authorized roles complete task; unauthorized access blocked; failures can be resolved | NOT RUN |
| UAT-03-1 | month-end close | happy path | Business owner confirms expected state transitions and ledger/data effects | NOT RUN |
| UAT-03-2 | month-end close | invalid/missing input | System rejects or correctly routes invalid data without silent corruption | NOT RUN |
| UAT-03-3 | month-end close | roles and exception handling | Authorized roles complete task; unauthorized access blocked; failures can be resolved | NOT RUN |
| UAT-04-1 | inventory receiving | happy path | Business owner confirms expected state transitions and ledger/data effects | NOT RUN |
| UAT-04-2 | inventory receiving | invalid/missing input | System rejects or correctly routes invalid data without silent corruption | NOT RUN |
| UAT-04-3 | inventory receiving | roles and exception handling | Authorized roles complete task; unauthorized access blocked; failures can be resolved | NOT RUN |

## Exit criteria
All critical flows passed with signed business-owner evidence, zero unresolved critical defects, and documented reconciliation. An AI-generated test document is not itself proof of testing.

