# Acme SaaS — Data Storage & Residency Policy

## Primary Storage Regions
Customer data is stored in AWS us-east-1 (N. Virginia) as the primary region, with
warm-standby replication to us-west-2 (Oregon) for disaster recovery. EU customer data
can optionally be hosted in eu-west-1 (Ireland) under our EU Data Residency add-on
(contact sales for provisioning).

## Data Classification
Customer data is classified as Confidential by default. Internal telemetry (logs, metrics)
is classified as Internal. No customer payload is sent to third-party analytics tools.

## Retention
Active customer data is retained for the duration of the contract. Upon contract termination,
data is deleted within 30 days. Backups are retained for 35 days on a rolling basis and then
purged.

## Sub-processors
A list of sub-processors (AWS, Datadog, Stripe, Postmark) is published at
acmesaas.com/trust/subprocessors and updated 30 days before any change.

## Cross-Border Transfer
For EU-to-US data transfers, Acme SaaS relies on the EU-US Data Privacy Framework and Standard
Contractual Clauses. Customers can request a signed DPA from legal@acmesaas.com.
