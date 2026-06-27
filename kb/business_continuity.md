# Acme SaaS — Business Continuity & Disaster Recovery

## Business Continuity Plan
Acme SaaS maintains a documented Business Continuity Plan (BCP) reviewed and tested annually.
The plan covers critical business functions including customer-facing services, internal
communications, and financial operations.

## Recovery Objectives
- **RPO (Recovery Point Objective)**: 1 hour for production databases, 24 hours for internal systems.
- **RTO (Recovery Time Objective)**: 4 hours for production services, 24 hours for non-critical systems.

## Backup Strategy
- Continuous replication to secondary AWS region (us-west-2).
- Hourly incremental backups with daily full snapshots.
- Backup encryption matches production encryption standards (AES-256).
- Monthly restore tests with documented results.

## DR Testing
Quarterly disaster recovery drills are conducted with full documentation.
Results are reviewed by leadership and available for SOC 2 audit evidence.

## Communication Plan
During a disruption, the Incident Response team activates the communication plan:
- Internal: Slack + PagerDuty escalation
- External: status.acmesaas.com updates + direct customer email
- Target: Customer notification within 2 hours of confirmed impact
