# Logout and Session Testing

## 1. Purpose

Verify that authenticated users can log out successfully, unauthenticated users cannot access protected logout functionality, and Django sessions are properly invalidated after logout.

## 2. API Endpoints

| Endpoint | Method | Access |
|---|---|---|
| `/api/accounts/login/` | POST | Public |
| `/api/accounts/logout/` | POST | Authenticated users only |
| `/api/accounts/me/` | GET | Authenticated users only |

## 3. Test Scenarios

| Test ID | Test Scenario | Expected Result |
|---|---|---|
| LOG-01 | Authenticated user logs out | HTTP 200; successful logout message |
| LOG-02 | Unauthenticated user attempts logout | HTTP 403; access denied |
| LOG-03 | User logs in through email and password | HTTP 200; authenticated session created |
| LOG-04 | Logged-in user accesses current-user endpoint | HTTP 200; user details returned |
| LOG-05 | User logs out after accessing protected endpoint | HTTP 200; session cleared |
| LOG-06 | User accesses protected endpoint after logout | HTTP 403; access denied |

## 4. Session Flow Verification

The complete session flow was tested using the same test client:

1. Log in using valid email and password.
2. Verify that Django creates an authenticated session.
3. Access the protected current-user endpoint.
4. Log out using the logout endpoint.
5. Verify that the authenticated session is cleared.
6. Attempt to access the protected endpoint again.
7. Confirm that access is denied.

## 5. Test Environment

- Framework: Django REST Framework
- Authentication: Django Session Authentication
- Database: PostgreSQL (temporary test database)
- Test framework: Django APITestCase

## 6. Execution Command

Run the following command from the backend directory:

```powershell
python manage.py test accounts
```

## 7. Test Results

- Test status: Passed
- Total accounts