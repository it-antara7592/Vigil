# Account Management

## 1. Overview

Vigil supports two types of registered accounts:

- **Learner:** A registered user who accesses learning activities and saves personal learning progress.
- **Administrator:** An authorised user responsible for platform administration and content management.

Guests can access permitted learning activities without creating an account. Guest identity, session management and usage tracking are handled separately from registered accounts.

Administrator registration is not publicly available. Administrator accounts are provisioned through a restricted management process.

## 2. Account Roles

| Account type | Description |
|---|---|
| Guest | Unregistered visitor with limited access to quizzes and simulations. |
| Learner | Registered user with access to personal learning history and reports. |
| Administrator | Authorised user with administrative responsibilities. |

The registered account role is stored in the `Profile` model.

The `Profile.role` field supports:

- `LEARNER`
- `ADMIN`

Guest is not a registered account role and does not have a `Profile` record.

### Administrator permissions

Vigil administrators use:

- `Profile.role = ADMIN`
- Django `is_staff = True`
- Django `is_superuser = False`

The Vigil application role and Django's built-in staff and superuser flags serve different purposes.

Administrators should receive only the specific Django model permissions required for their responsibilities. Broad superuser privileges are not granted automatically.

## 3. Registration and Authentication

### Registration

Learners register using:

- First name (required)
- Last name (optional)
- Username
- Email address
- Password
- Confirm password

Username and email addresses must be unique, with case-insensitive duplicate checks.

Passwords are validated using Django's configured password validators.

Email verification is not implemented in the current version. A valid email format does not establish that the mailbox exists or belongs to the user.

New registrations receive the `LEARNER` role by default.

### Login

Users authenticate using their email address and password.

Vigil uses Django session-based authentication through Django REST Framework's `SessionAuthentication`.

The authentication backend checks:

- Email and password validity.
- Whether the account is active.
- Whether a pending account deletion has passed its scheduled deletion time.

An account whose deletion grace period has expired cannot log in, even if the permanent deletion management command has not yet run.

### Logout

Authenticated users can log out, terminating their current authenticated session.

### Current-user endpoint

The authenticated user can retrieve their own account information through the current-user endpoint.

## 4. Guest Identity and Session Management

Guest access is supported without creating a registered user account.

Vigil separates a guest's persistent identity from their temporary access session. This allows guest usage allowances to remain associated with the same visitor even when an individual session expires.

### Guest identity

The `GuestIdentity` model represents a guest visitor across multiple sessions.

It stores:

- Hashed identity token
- Creation timestamp
- Last meaningful activity timestamp
- Expiry timestamp

A guest identity:

- Has a 60-day inactivity lifetime.
- Persists across browser restarts through a persistent browser cookie.
- Owns the guest's usage records.
- Can be associated with multiple sessions over time.

The identity lifetime is renewed through meaningful guest activity, rather than simply validating or retrieving an existing guest session.

When an identity expires, it is eligible for deletion. Its associated guest sessions and usage records are configured to be deleted through database cascading relationships.

### Guest session

The `GuestSession` model represents an individual period of guest access.

It stores:

- Associated guest identity
- Hashed session token
- Creation timestamp
- Last activity timestamp
- Expiry timestamp
- Active/inactive status

Each guest session has a 24-hour lifetime.

A guest identity can have multiple historical sessions, but the database enforces a maximum of one active session per identity.

When a session expires while its identity remains valid, a new session can be created without replacing the identity. Existing guest usage records remain associated with that identity.

### Guest tokens and cookies

Vigil uses two separate opaque, cryptographically generated tokens:

| Cookie | Purpose | Lifetime |
|---|---|---|
| `vigil_guest_identity` | Recognises the returning guest identity. | Up to 60 days, subject to identity expiry. |
| `vigil_guest_session` | Identifies the current guest access session. | 24 hours. |

Only SHA-256 hashes of these tokens are stored in the database. Raw tokens are not stored in database records.

Both cookies are configured as:

- HttpOnly
- SameSite Lax
- Path `/`
- Secure in production

The Secure attribute is disabled in local development when Django `DEBUG` is enabled, allowing cookies to work over local HTTP.

The identity cookie and session cookie have separate lifetimes. Expiry of the session cookie does not automatically mean the guest identity or its usage records have expired.

### Guest lifecycle

The expected lifecycle is:

1. A visitor accesses guest functionality without existing guest cookies.
2. Vigil creates a guest identity and an associated guest session.
3. The browser receives separate identity and session cookies.
4. On a returning visit, Vigil validates the available identity and session tokens.
5. If the identity is valid but the session has expired, Vigil creates a new session under the existing identity.
6. If the identity has expired or is unavailable, a new guest identity and session are created.
7. Meaningful guest activity renews the identity's inactivity lifetime without extending the current session's 24-hour expiry.

Invalid or expired tokens must not grant access to an existing guest session.

### Guest registration and login transition

When a guest successfully registers or logs in:

- The current guest session is invalidated.
- Both guest cookies are cleared from the browser.
- Future activity uses the registered account.

The guest identity is not immediately deleted. Its usage records remain associated with it until the identity's normal expiry and cleanup.

Guest learning history is not automatically merged into the newly registered account in the current implementation.

## 5. Guest Usage Tracking

Guest usage is stored separately from registered-user learning history.

The `GuestUsage` model records usage by:

- Guest identity
- Usage type
- Week start date
- Used count

Supported usage types currently include:

- `QUIZ`
- `SIMULATION`

A database uniqueness constraint prevents multiple usage records for the same guest identity, usage type and week.

### Weekly period

Guest weekly periods begin on Monday at 00:00 Indian Standard Time (IST).

The weekly period calculation explicitly uses the `Asia/Kolkata` timezone, independently of the project's default UTC timezone.

### Allowance ownership

Guest usage belongs to the persistent guest identity, not the temporary guest session.

Consequently:

- Browser restarts do not reset usage.
- Expiry of a 24-hour session does not reset usage.
- Creating a replacement session does not reset usage.
- A new weekly period uses a new week-start record.

### Allowance implementation status

The guest identity, session and usage data structures are implemented.

The current implementation also includes the weekly-period calculation.

The following are not yet implemented:

- Atomic weekly allowance consumption.
- Enforcement of the agreed quiz and simulation limits.
- Integration of allowance consumption with actual quiz-attempt and simulation-session creation.
- Automated cleanup of expired guest identities.

These features must be implemented before the guest allowance system is considered complete.

## 6. Account Deletion

Vigil provides a recoverable account deletion process rather than immediately deleting accounts when a request is submitted.

### Grace periods

| Account role | Grace period |
|---|---:|
| Learner | 15 days |
| Administrator | 30 days |

A deletion request is stored in the `AccountDeletionRequest` model.

Each request records its status and relevant timestamps.

### Deletion request statuses

| Status | Meaning |
|---|---|
| `PENDING` | Deletion has been requested and the grace period is in progress or awaiting required conditions. |
| `CANCELLED` | The user successfully recovered the account during the grace period. |
| `COMPLETED` | Permanent account deletion was processed. |

Only one pending deletion request is permitted per user.

### Automatic cancellation through login

A successful login during the grace period automatically cancels the pending deletion request.

No separate cancellation confirmation is required.

The following rules apply:

- Successful authentication within the grace period cancels the request.
- Failed authentication does not cancel the request.
- Login after the scheduled deletion time is rejected.
- Existing authenticated sessions are also invalidated when Django retrieves the user after the scheduled deletion time.

When a request is cancelled, the cancellation timestamp is recorded.

### Deletion cooldown

After cancelling a pending deletion request, a user must wait 10 days before submitting another deletion request.

The cooldown begins at the cancellation timestamp.

Once the cooldown expires, the user can submit another request. There is no lifetime limit on deletion requests.

### Permanent deletion

Permanent deletion is handled by the `process_account_deletions` Django management command.

The command processes eligible pending requests whose scheduled deletion time has passed.

When a learner's request becomes eligible:

1. The account is identified.
2. The deletion request is marked `COMPLETED`.
3. A permanent deletion audit event is recorded.
4. The user account is deleted.
5. Related personal records are handled according to their database relationship deletion policies.

The user model's deletion cascades to the associated profile and other personal records configured with cascading deletion.

The deletion request and security audit records use `SET_NULL` relationships for user references, allowing limited operational history to remain without retaining the deleted user relationship.

The management command currently requires manual execution. Automatic scheduling through an appropriate operating-system or deployment scheduler is still pending.

## 7. Administrator Succession

Administrator deletion requires additional safeguards to prevent the platform from losing its administrative access.

### Replacement nomination

An administrator must nominate a replacement email address when requesting account deletion.

The administrator receives a 30-day grace period.

The nominated replacement cannot be the administrator's own account.

### Appointment approval

Administrator replacement requires approval from at least two of the three project owners.

This approval takes place outside the Vigil application.

The technical maintainer verifies the approval and records the identities of the two approving project owners during the provisioning process.

The technical maintainer performs the technical provisioning but does not independently make the appointment decision.

### Replacement provisioning

The `provision_admin` management command provisions the replacement administrator.

The nominated replacement can be:

- An existing active learner account, which is promoted to administrator.
- A new account created for the nominated email address.

The replacement receives:

- `Profile.role = ADMIN`
- `is_staff = True`
- `is_superuser = False`

The command validates the password of a newly created account using Django's configured password validators.

After provisioning, the replacement is linked to the administrator's pending deletion request.

The approval timestamp is recorded.

### Replacement login confirmation

The replacement administrator must log in successfully before the original administrator can be permanently deleted.

A successful login records the replacement confirmation timestamp.

The replacement must remain eligible when permanent deletion is processed.

### Conditions for permanent deletion

An administrator's account can be permanently deleted only when:

1. The 30-day grace period has expired.
2. A replacement administrator is linked to the request.
3. The replacement account is active.
4. The replacement is not a Django superuser.
5. The replacement has Django staff access.
6. The replacement has the Vigil administrator role.
7. The replacement is not the administrator whose account is being deleted.
8. The replacement does not have its own pending deletion request.
9. The replacement appointment has been approved.
10. The replacement has successfully logged in and confirmed access.

If these conditions are not satisfied, permanent deletion is postponed.

The old administrator's account remains pending deletion until the required succession conditions are met.

## 8. Security Audit Logging

Vigil uses a reusable `SecurityAuditLog` model for recording important security and administrative events.

The audit system is introduced incrementally, beginning with account-related events.

Examples include:

- Successful login
- Logout
- Account deletion request
- Account deletion cancellation
- Administrator replacement provisioning
- Administrator replacement access confirmation
- Permanent account deletion

### Recorded information

The audit model supports:

- Actor reference
- Action
- Target type
- Target identifier
- Metadata
- Event timestamp

The actor reference uses `SET_NULL` so that historical audit records can remain after an account is deleted.

### Audit data protection

Audit records should contain only information necessary for security and accountability.

Passwords, authentication tokens, session identifiers and sensitive message contents must not be recorded.

Guest identity tokens and guest session tokens must not be recorded in audit metadata.

Access to audit records should be restricted.

The audit system is intended to support future administrative and content-management events as the learning, assessment and simulation modules are developed.

Retention periods and operational access controls must be defined before production deployment. Audit records should not be retained indefinitely without justification.

## 9. Database Models and Constraints

The account-management functionality currently uses the following models:

| Model | Responsibility |
|---|---|
| `Profile` | Stores the registered user's Vigil role. |
| `AccountDeletionRequest` | Tracks deletion requests, grace periods, cancellations and administrator succession. |
| `SecurityAuditLog` | Records important security and administrative events. |
| `GuestIdentity` | Represents a persistent unregistered visitor identity. |
| `GuestSession` | Represents an individual guest access session. |
| `GuestUsage` | Records weekly guest usage by activity type. |

### Important database constraints

`AccountDeletionRequest` enforces:

- Only one pending deletion request per user.
- A replacement administrator cannot be linked to multiple pending administrator deletion requests.

The second constraint applies only when:

- The request status is `PENDING`.
- The request role is `ADMIN`.
- The replacement user is not null.

`GuestSession` enforces:

- A unique session token hash.
- A maximum of one active session per guest identity.

`GuestUsage` enforces:

- One usage record per guest identity, usage type and week start date.

These constraints provide database-level protection in addition to application-level validation.

## 10. API Endpoints

Account endpoints are registered under:

`/api/accounts/`

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/accounts/register/` | Register a learner account. |
| POST | `/api/accounts/login/` | Authenticate using email and password. |
| POST | `/api/accounts/logout/` | End the authenticated session. |
| GET | `/api/accounts/me/` | Retrieve the authenticated user's account information. |
| GET | `/api/accounts/deletion-request/` | Retrieve the current user's pending deletion request. |
| POST | `/api/accounts/deletion-request/` | Submit an account deletion request. |
| POST | `/api/accounts/guest-session/` | Create or retrieve a guest identity and session. |

Public registration, login and guest-session endpoints permit unauthenticated access. User-specific endpoints require authentication.

The guest-session endpoint uses cookies to identify an existing guest identity and session or establish new ones.

## 11. Management Commands

The account application currently includes two management commands.

| Command | Purpose |
|---|---|
| `process_account_deletions` | Processes eligible permanent account deletion requests. |
| `provision_admin` | Provisions an approved replacement administrator. |

Run these commands from the backend directory with the Python virtual environment activated.

```powershell
python manage.py process_account_deletions
```

```powershell
python manage.py provision_admin
```

The deletion command requires an appropriate execution schedule before production deployment.

Expired guest identity cleanup is not yet implemented as a management command.

## 12. Current Implementation Status

| Functionality | Status |
|---|---|
| Learner registration | Implemented |
| Email and password authentication | Implemented |
| Session-based authentication | Implemented |
| Logout | Implemented |
| Current-user endpoint | Implemented |
| Learner account deletion request | Implemented |
| Administrator deletion request | Implemented |
| Automatic deletion cancellation on successful login | Implemented |
| 10-day deletion cooldown | Implemented |
| Permanent deletion management command | Implemented |
| Administrator replacement provisioning | Implemented |
| Replacement login confirmation | Implemented |
| Security audit event model and initial account events | Implemented |
| Guest identity model | Implemented |
| Guest session model | Implemented |
| Guest usage model | Implemented |
| Hashed guest token storage | Implemented |
| Separate guest identity and session cookies | Implemented |
| 60-day guest identity inactivity lifetime | Implemented |
| 24-hour guest session lifetime | Implemented |
| Guest session recreation while preserving identity | Implemented |
| Guest session invalidation on successful registration/login | Implemented |
| Monday 00:00 IST weekly-period calculation | Implemented |
| Atomic guest allowance consumption | Pending |
| Guest quiz and simulation allowance enforcement | Pending |
| Expired guest identity cleanup command | Pending |
| Automatic scheduling of permanent deletion | Pending |
| Email verification and password recovery | Deferred |
| Detailed audit retention policy | Pending |
| Fine-grained administrator permissions | Pending |
| CSRF and production cookie security configuration | Pending |

## 13. Future Considerations

The account architecture should remain extensible as Vigil develops.

Potential future improvements include:

- Email verification.
- Password recovery.
- Additional administrator authentication safeguards.
- Defined audit retention and archival policies.
- Fine-grained administrator permissions.
- Integration of the audit system with learning, assessment and simulation management.
- Atomic guest usage allowance enforcement.
- Scheduled cleanup of expired guest identities.

These improvements should be introduced when their requirements are agreed upon and should not be treated as currently implemented functionality.