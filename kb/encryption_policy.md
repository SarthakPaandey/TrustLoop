# Acme SaaS — Encryption Policy

## Encryption at Rest
All customer data is encrypted at rest using AES-256 (Advanced Encryption Standard, 256-bit keys).
This includes primary databases (PostgreSQL), object storage (S3), and backups. Encryption keys
are managed in AWS KMS with automatic annual rotation.

## Encryption in Transit
All network traffic between clients and Acme SaaS services is encrypted using TLS 1.2 or TLS 1.3.
Older TLS versions and SSL are disabled at the load balancer. Internal service-to-service traffic
inside the production VPC is also TLS-encrypted via the service mesh.

## Key Management
Customer encryption keys are stored in AWS KMS. Acme SaaS does not currently offer customer-managed
keys (CMK / BYOK); all keys are platform-managed. Key access is restricted to a small SRE group
and every access event is audit-logged.

## Hashing of Credentials
User passwords are never stored in plaintext. Acme SaaS uses bcrypt with a work factor of 12.
Password reset tokens are single-use and expire after 30 minutes.
