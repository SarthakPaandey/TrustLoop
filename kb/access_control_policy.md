# Acme SaaS — Access Control Policy

## Authentication
All Acme SaaS customer accounts support email/password authentication with bcrypt password hashing.
Single Sign-On (SSO) via SAML 2.0 and OIDC is available on Business and Enterprise plans.
Supported identity providers include Okta, Azure AD, Google Workspace, and any SAML 2.0-compliant IdP.

## Multi-Factor Authentication (MFA)
MFA is supported for all plans and enforced by default on Enterprise. Supported factors are
TOTP authenticator apps and WebAuthn / FIDO2 security keys. SMS-based MFA is not offered.

## Role-Based Access Control
Acme SaaS supports four built-in roles: Owner, Admin, Member, and Read-Only. Custom roles with
granular permissions are available on the Enterprise plan.

## Internal Access
Acme SaaS employee access to production systems requires (1) SSO with MFA, (2) just-in-time
elevation via our internal access broker, and (3) full session recording. Access to customer
data requires a documented support ticket and is audit-logged.

## Audit Logs
Customer-visible audit logs cover authentication events, role changes, data exports, and API key
usage. Logs are retained for 90 days on Business and 1 year on Enterprise.
