# Acme SaaS — Network Security Architecture

## VPC Design
Production infrastructure runs in a dedicated AWS account with a segmented VPC.
Network tiers are isolated using separate subnets and security groups:
- **Public tier**: Load balancers, WAF, bastion hosts
- **Application tier**: API servers, worker processes
- **Data tier**: Databases, caches, message queues

## Firewall & WAF
- All ingress traffic passes through AWS WAF with managed rule sets (OWASP Top 10, rate limiting).
- No direct internet ingress to application servers.
- Egress is restricted via a NAT gateway with allowlisted destinations.
- Security groups follow least-privilege: only explicitly allowed traffic is permitted.

## DDoS Protection
AWS Shield Standard is enabled for all public endpoints. AWS Shield Advanced is
available for Enterprise customers requiring enhanced DDoS mitigation.

## Internal Service Mesh
Service-to-service communication uses mTLS via an Istio service mesh. All internal
traffic is encrypted and authenticated.

## DNS & CDN
- DNS is managed via Route 53 with DNSSEC enabled.
- Static assets are served via CloudFront with origin access control.
- TLS termination happens at the load balancer; no plaintext traffic reaches application servers.

## Network Monitoring
- VPC Flow Logs are enabled and retained for 90 days.
- AWS GuardDuty is enabled for threat detection.
- Anomaly detection alerts on unusual traffic patterns, port scanning, and data exfiltration attempts.
