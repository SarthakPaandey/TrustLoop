# Acme SaaS — Human Resources & Employee Security

## Background Checks
All employees undergo background checks upon hire, including criminal history and employment
verification, where legally permissible. Contractors with access to production systems undergo
equivalent screening.

## Security Awareness Training
- All employees complete mandatory security awareness training within 30 days of hire.
- Annual refresher training is required for all staff.
- Monthly phishing simulations are conducted; employees who fail receive additional training.
- Security team conducts quarterly lunch-and-learn sessions on emerging threats.

## Device Management
- All company laptops are managed via MDM (Jamf for macOS, Intune for Windows).
- Full-disk encryption (FileVault / BitLocker) is enforced on all devices.
- Screen lock activates after 5 minutes of inactivity.
- EDR (CrowdStrike Falcon) is deployed on all endpoints.
- Personal devices are not permitted to access production systems.

## Access Reviews
- Quarterly access reviews are conducted for all production systems.
- Former employee access is revoked within 4 hours of termination.
- Vendor access is reviewed monthly and revoked when no longer needed.

## Clean Desk Policy
Employees are expected to follow a clean desk policy. Sensitive documents must be
locked away or shredded. Whiteboards containing sensitive information must be erased
after meetings.
