# Incident Response Runbook

This runbook describes how Example Corp detects, escalates and communicates production incidents on the AI platform.

## 1 Severity levels

| Severity | Customer impact | First response | Status page update |
|---|---|---|---|
| SEV1 | Platform unavailable or data exposure | 5 minutes | Every 30 minutes |
| SEV2 | Major feature degraded for many customers | 15 minutes | Every 60 minutes |
| SEV3 | Minor degradation or single customer | 4 hours | Not required |

## 2 Escalation

### 2.1 Paging

The on-call engineer is paged automatically when an alert fires. If the page is not acknowledged within 10 minutes, it escalates to the secondary on-call.

### 2.2 Incident commander

For SEV1 and SEV2, the first responder appoints an incident commander. The commander owns decisions and communication; responders own investigation and mitigation.

## 3 Mitigation

Prefer rollback over forward fixes. A change that correlates with the start of an incident is rolled back first and investigated afterwards[^1].

- Feature flags are switched off before code is reverted.
- Database migrations are never rolled back without the data team.

## 4 Communication

Customers hear about SEV1 incidents from the status page first. Account teams contact affected enterprise customers directly within 1 hour.

## 5 Postmortem

A blameless postmortem is written for every SEV1 and SEV2 within 5 business days. Action items have owners and due dates and are tracked to completion.

[^1]: Rollback is skipped only when the change cannot be safely reverted, such as an irreversible schema migration.
