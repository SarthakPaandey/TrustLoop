# Acme SaaS — General Security Practices

## Secure Development Lifecycle
Acme SaaS follows a secure SDLC: peer-reviewed pull requests, mandatory static analysis (Semgrep),
dependency scanning (Snyk / GitHub Dependabot), and container image scanning (Trivy) on every
build. Production deploys require two reviewer approvals.

## Vulnerability Management
- Critical vulnerabilities: remediated within 7 days.
- High: 30 days. Medium: 90 days. Low: best effort.
- Patch cadence is tracked in our internal Jira and reported in our SOC 2 audit.

## Employee Security
All employees complete annual security awareness training and phishing simulations.
Background checks are performed on hire (where legally permissible). Laptops are
managed via MDM with full-disk encryption, screen lock, and EDR (CrowdStrike).

## Network Architecture
Production runs in a dedicated AWS account with a segmented VPC. No direct internet ingress to
application servers; all traffic flows through a managed WAF and load balancer. Egress is
restricted via a NAT gateway with allowlisted destinations.

## Logging & Monitoring
Centralized logging via Datadog and AWS CloudTrail. Security-relevant logs are retained for
13 months. Anomaly detection is in place for failed auth, privilege escalation, and unusual
data exfiltration patterns.
