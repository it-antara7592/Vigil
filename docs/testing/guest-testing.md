# Guest Identity and Session Testing

## 1. Overview

Vigil supports guest access without requiring visitors to create registered accounts.

Guest functionality uses three database models:

- `GuestIdentity`
- `GuestSession`
- `GuestUsage`

Guest identity persists across multiple sessions, while each individual guest session has a separate expiry period.

The guest test suite verifies identity creation, session management, token validation, cookie handling, activity renewal and weekly-period calculation.

Tests are maintained in:

`backend/accounts/tests.py`

## 2. Running Guest Tests

Run commands from the backend directory with the project's Python virtual environment activated.

### Run the complete account test suite

```powershell
python manage.py test accounts
```

This includes both registered-account tests and guest tests.

### Run guest identity and session lifecycle tests

```powershell
python manage.py test accounts.tests.GuestIdentityAndSessionTests
```

### Run weekly period tests

```powershell
python manage.py test accounts.tests.GuestWeeklyPeriodTests
```

### Run guest session endpoint tests

```powershell
python manage.py test accounts.tests.GuestSessionEndpointTests
```

### Run guest authentication transition tests

```powershell
python manage.py test accounts.tests.GuestAuthenticationTransitionTests
```

## 3. Guest Identity and Session Lifecycle

`GuestIdentityAndSessionTests`

This test class verifies the separation between persistent guest identity and temporary guest sessions.

### Identity creation and token security

Tests verify:

- Guest tokens are generated securely.
- Generated tokens are distinct.
- Only SHA-256 token hashes are stored in the database.
- Raw guest tokens are not stored in database records.
- Guest identity and session expiry periods are configured correctly.

### Identity and session reuse

Tests verify:

- A valid guest identity and session can be reused.
- Retrieving an existing guest does not incorrectly renew the identity lifetime.
- A missing session can be recreated under an existing valid identity.
- A missing identity results in a new identity and session.

### Session expiry and recreation

Tests verify:

- An expired guest session is replaced.
- The replacement session belongs to the existing guest identity.
- Existing guest usage records remain associated with the identity.
- Creating a new session deactivates the previous active session.
- A guest identity cannot have multiple active sessions.

### Guest identity expiry

Tests verify:

- An expired guest identity is deleted when the guest is retrieved.
- A new identity and session are created after the previous identity expires.
- Associated guest sessions and usage records are deleted through configured cascading relationships.

## 4. Guest Session Validation

The guest lifecycle tests verify that session validation:

- Accepts valid identity and session tokens.
- Rejects missing tokens.
- Rejects incorrect tokens.
- Rejects expired sessions.
- Rejects inactive sessions.
- Rejects sessions associated with expired identities.
- Does not unintentionally update identity or session activity timestamps.

Session validation must not be confused with meaningful guest activity. Merely checking whether a session is valid should not renew the guest identity's inactivity lifetime.

## 5. Meaningful Guest Activity

The tests verify that meaningful activity:

- Renews the guest identity's 60-day inactivity lifetime.
- Updates the relevant activity timestamps.
- Does not extend the current session's 24-hour expiry.
- Rejects missing, inactive or expired sessions.

This keeps identity persistence and individual session expiry independent.

## 6. Ending a Guest Session

The guest lifecycle tests verify that ending a guest session:

- Marks the session inactive.
- Preserves the guest identity.
- Preserves guest usage records.
- Rejects invalid or missing tokens.

Ending a session does not immediately delete the guest identity.

## 7. Weekly Guest Period Calculation

`GuestWeeklyPeriodTests`

Guest usage periods are calculated using Indian Standard Time (`Asia/Kolkata`).

The weekly period begins every Monday at 00:00 IST.

Tests verify:

- Correct calculation of the Monday week-start date.
- Correct handling of timestamps around the weekly boundary.
- Conversion of UTC timestamps into IST before determining the week-start date.

These tests verify the weekly-period calculation, not the complete allowance enforcement system.

## 8. Guest Session API Endpoint

`GuestSessionEndpointTests`

The guest session endpoint is:

`POST /api/accounts/guest-session/`

Tests verify:

- A first-time guest request creates a guest identity and session.
- The response sets separate identity and session cookies.
- Both cookies use HttpOnly.
- Both cookies use SameSite Lax.
- A returning guest can reuse valid cookies.
- An expired session can be replaced while preserving the identity.

The endpoint allows unauthenticated visitors to establish or retrieve guest access.

## 9. Guest-to-Registered Account Transition

`GuestAuthenticationTransitionTests`

When a guest registers or logs in successfully, Vigil transitions future activity to the registered account.

Tests verify:

- Successful registration invalidates the active guest session.
- Successful registration clears the guest cookies.
- Successful login invalidates the active guest session.
- Successful login clears the guest cookies.
- Failed login does not invalidate the guest session.

The guest identity and its usage records are not immediately deleted during this transition.

Guest learning history is not automatically merged into a newly registered account in the current implementation.

## 10. Current Test Results

The complete account test suite, including guest functionality, has successfully completed with the following result:

| Test result | Count |
|---|---:|
| Tests found | 75 |
| Tests run | 75 |
| Failures | 0 |
| Errors | 0 |
| Final result | Passed |

Django also reported:

`System check identified no issues (0 silenced).`

The test database was successfully created and destroyed after execution.

This result applies to the implementation at the time of the successful test run. The test count may change as additional functionality is developed.

## 11. Guest Features Not Yet Implemented

The current guest tests verify identity and session management, but the complete guest allowance system is not yet implemented.

| Feature | Status |
|---|---|
| Guest identity creation | Implemented |
| Guest session creation | Implemented |
| Hashed token storage | Implemented |
| Separate identity and session cookies | Implemented |
| Identity and session expiry | Implemented |
| Guest session recreation | Implemented |
| Meaningful activity renewal | Implemented |
| Guest session invalidation on successful registration/login | Implemented |
| Weekly period calculation using IST | Implemented |
| Guest usage database model | Implemented |
| Atomic weekly allowance consumption | Pending |
| Quiz allowance enforcement | Pending |
| Simulation allowance enforcement | Pending |
| Integration with actual quiz and simulation attempt creation | Pending |
| Expired guest identity cleanup command | Pending |
| Scheduled guest identity cleanup | Pending |

The existence of the `GuestUsage` model does not mean that weekly allowances are already being consumed or enforced.

## 12. Testing Guidelines

When modifying guest functionality:

1. Add or update tests for the affected behaviour.
2. Test both valid and invalid token scenarios.
3. Verify identity expiry independently from session expiry.
4. Verify that session recreation preserves identity-based usage.
5. Test weekly boundaries using IST.
6. Verify that registration and login invalidate the guest session correctly.
7. Run the complete account test suite before committing account changes.

Useful verification commands:

```powershell
python manage.py test accounts
```

```powershell
python manage.py check
```

```powershell
python manage.py makemigrations --check --dry-run
```

```powershell
git diff --check
```

Future allowance enforcement, cleanup and security changes must include their own tests before being considered complete.