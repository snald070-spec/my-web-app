# Play Console Submission Draft (2026-04-11)

## 1) App Access (for Play review)
Use this text in Play Console > App content > App access.

- App requires login credentials.
- There is no public self-signup.
- Test account provisioning method:
  - Provide reviewer account ID/password through Play Console "App access" field.
- Login path:
  - App launch -> Login screen -> enter credentials.
- Scope after login:
  - General members: attendance/league/fee status.
  - Admin/Master: user management and fee management screens.

## 2) Privacy Policy draft points (source-of-truth)
Use this as policy content basis.

- Collected account/profile data:
  - employee ID (or account ID), name, role, department/division, optional email
- Collected service-operation data:
  - attendance votes, league participation/results, fee payment status/history
- Collected bank matching data (admin flow):
  - depositor name, amount, occurrence time, matching status
- Authentication/security:
  - hashed password storage on server, JWT session token usage
- Data usage purposes:
  - authentication and access control
  - attendance/league/fee service operation
  - admin audit and security monitoring
- Data sharing:
  - no active third-party ad/analytics data sharing flow confirmed in current release configuration
  - note: `google-services` classpath exists, but `google-services.json` is absent so plugin is not applied in this build
- Encryption in transit:
  - production API is HTTPS-only by runtime guard and Android network security config

## 3) Data safety form draft (Play)
Mark these as draft values to start from.

### Data collected
- Personal info:
  - Name (Yes, collected)
  - Email (Yes, optional)
  - User IDs (Yes, employee/account ID)
- Financial info:
  - Payment history/amount status (Yes, for membership fee operation)
- App activity:
  - In-app actions related to attendance/league/fee records (Yes)

### Data shared
- No data sharing flow confirmed in current release build configuration (draft: No)

### Collection purpose (draft)
- App functionality
- Account management
- Security/fraud prevention

### Encryption in transit
- Yes (draft)

### Data deletion request
- Account lifecycle is admin-managed.
- Admin deletion endpoints exist (`/api/users/{emp_id}`, `/api/users/bulk-delete`), but no self-service user deletion UI/flow was confirmed.
- Play policy action needed:
  - publish a clear deletion request channel in privacy policy (email/form)
  - if account deletion is required by policy scope, provide user-accessible deletion mechanism

## 4) Content rating and declarations checklist
- Complete questionnaire based on sports/community app behavior.
- Confirm no ads, no gambling, no health/medical claim content.
- Confirm no background location/camera/mic permission in main manifest.

## 5) Evidence from codebase (quick references)
- Main Android permission:
  - INTERNET only in main manifest
- Release signing:
  - release signingConfig active with upload keystore
- Security hardening:
  - allowBackup=false, cleartext blocked in main, dataExtractionRules configured

## 6) Reviewer package to prepare
- Internal test release notes
- Reviewer test account credentials
- Privacy policy public URL
- Data safety answers finalized from this draft
