# Acme SaaS — Incident Response & Business Continuity

## Incident Response Program
Acme SaaS maintains a documented Incident Response Plan reviewed annually. The SecOps team
operates a 24/7 on-call rotation with paging via PagerDuty. Security incidents are triaged within
30 minutes of detection.

## Customer Notification SLA
For confirmed security incidents involving customer data, Acme SaaS notifies affected customers
within 72 hours of confirmation. Notifications include scope, root cause once known, and remediation
steps. We do NOT guarantee zero breaches — no provider can truthfully make such a claim — but we
do commit to transparent, timely disclosure.

## Availability
Acme SaaS targets 99.9% monthly uptime on Business and 99.95% on Enterprise, backed by service
credits per our SLA. Status is published at status.acmesaas.com.

## Disaster Recovery
- RPO (Recovery Point Objective): 1 hour
- RTO (Recovery Time Objective): 4 hours
- DR drills are executed quarterly with documented results retained for SOC 2 evidence.

## Backups
Encrypted backups are taken hourly (incremental) and daily (full) and replicated to a secondary
region. Restore tests are performed monthly.
