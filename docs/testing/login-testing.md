# Vigil – Login Testing

## 1. Purpose

This document describes the automated tests for the Vigil login API.

The tests verify that:
- Users can log in using email and password.
- Email matching is case-insensitive.
- Invalid credentials are rejected.
- Inactive accounts cannot log in.
- Successful authentication creates a Django session.

## 2. API Under Test

| Property | Value |
|---|---|
| Endpoint | `/api/accounts/login/` |
| Method | POST |
| Authentication | Public (`AllowAny`) |
| Expected success status | 200 OK |
| Authentication method | Django Session Authentication |

## 3. Login Fields

| Field | Requirement |
|---|---|
| Email | Required |
| Password | Required |

Login uses email and password, not username.

## 4. Test Scenarios

| ID | Test scenario | Expected result |
|---|---|---|
| LOGIN-01 | Successful login | 200 OK and session created |
| LOGIN-02 | Email with different casing | 200 OK |
| LOGIN-03 | Incorrect password | 400 Bad Request |
| LOGIN-04 | Unknown email | 400 Bad Request |
| LOGIN-05 | Inactive account | 400 Bad Request |
| LOGIN-06 | Missing email | 400 Bad Request |
| LOGIN-07 | Missing password | 400 Bad Request |

## 5. Test Environment

- Framework: Django REST Framework `APITestCase`
- Database: Temporary Django test database
- Test module: `accounts/tests.py`

Test records are isolated from the development database.

## 6. Execution

Run all account tests from the backend directory:

```powershell
python manage.py test accounts
```


## 7. Test Results

Status: PASSED

- Total tests: 7
- Passed: 7
- Failed: 0
- Errors: 0

All login tests passed successfully.

The login tests were executed together with the registration
tests using a temporary Django test database.

The development database was not modified.


## 8. Maintenance

Whenever login or authentication behaviour changes, review and update the relevant automated tests.
