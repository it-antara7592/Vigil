# Vigil – Registration Testing

## 1. Purpose

This document describes the automated tests for the Vigil account registration API.

The tests verify that registration:
- Creates a valid learner account.
- Stores the first name and optional last name correctly.
- Creates the associated learner profile.
- Enforces unique usernames and email addresses, regardless of letter casing.
- Validates passwords and required fields.

## 2. API Under Test

| Property | Value |
|---|---|
| Endpoint | `/api/accounts/register/` |
| Method | POST |
| Authentication | Public (`AllowAny`) |
| Expected success status | 201 Created |

## 3. Registration Fields

| Field | Requirement | Django storage |
|---|---|---|
| First name | Required | `User.first_name` |
| Last name | Optional | `User.last_name` |
| Username | Required and unique | `User.username` |
| Email | Required and unique | `User.email` |
| Password | Required | Stored as a secure password hash |
| Confirm password | Required | Validation only; not stored |

## 4. Test Scenarios

| ID | Test scenario | Expected result |
|---|---|---|
| REG-01 | Successful registration | 201 Created; user and learner profile created |
| REG-02 | Registration without last name | 201 Created; last name remains empty |
| REG-03 | Duplicate email | 400 Bad Request |
| REG-04 | Duplicate email with different casing | 400 Bad Request |
| REG-05 | Duplicate username | 400 Bad Request |
| REG-06 | Duplicate username with different casing | 400 Bad Request |
| REG-07 | Password confirmation mismatch | 400 Bad Request |
| REG-08 | Weak password | 400 Bad Request |
| REG-09 | Missing email | 400 Bad Request |
| REG-10 | Missing required fields | 400 Bad Request |

## 5. Test Environment

- Framework: Django REST Framework `APITestCase`
- Database: Temporary Django test database
- Test module: `accounts/tests.py`

The automated tests use an isolated test database. Test records are not intended to remain in the development database.

## 6. Execution

Run the following command from the backend directory:

```powershell
python manage.py test accounts
```

## 7. Test Results

Status: PASSED

- Total tests: 10
- Passed: 10
- Failed: 0
- Errors: 0
- Execution time: 10.427 seconds

All registration tests passed successfully.

The temporary test database was destroyed after execution.
The development database was not modified.

## 8. Maintenance

Whenever registration validation or account creation logic changes, review and update the relevant automated tests.
