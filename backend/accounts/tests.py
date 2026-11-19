from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import (
    Profile,
    AccountDeletionRequest,
    SecurityAuditLog,
    GuestIdentity,
    GuestSession,
    GuestUsage,
)
from .services import (
    process_due_deletion_requests,
    generate_guest_token,
    hash_guest_token,
    create_guest_identity,
    create_guest_session,
    get_or_create_guest,
    validate_guest_session,
    record_guest_activity,
    get_current_guest_week_start,
    end_guest_session,
    GUEST_IDENTITY_LIFETIME_DAYS,
    GUEST_SESSION_LIFETIME_HOURS,
    GUEST_IDENTITY_COOKIE,
    GUEST_SESSION_COOKIE,
)

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command

from .models import Profile


User = get_user_model()


class RegistrationTests(APITestCase):

    url = '/api/accounts/register/'

    def registration_data(self, **overrides):
        data = {
            "first_name": "Test",
            "last_name": "Learner",
            "username": "testlearner",
            "email": "testlearner@example.com",
            "password": "Vigil-Test-Only-2026!xQ",
            "confirm_password": "Vigil-Test-Only-2026!xQ",
        }

        data.update(overrides)
        return data

    def register(self, data):
        return self.client.post(
            self.url,
            data,
            format='json'
        )

    def test_successful_registration(self):
        response = self.register(self.registration_data())

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username='testlearner')

        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'Learner')
        self.assertEqual(user.email, 'testlearner@example.com')
        self.assertTrue(user.check_password('Vigil-Test-Only-2026!xQ'))

        self.assertTrue(
            Profile.objects.filter(user=user, role='LEARNER').exists()
        )

    def test_registration_without_last_name(self):
        data = self.registration_data()
        data.pop('last_name')

        response = self.register(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username='testlearner')

        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, '')

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='Existing-Test-2026!xQ'
        )

        response = self.register(
            self.registration_data(email='existing@example.com')
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_email_with_different_casing_is_rejected(self):
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='Existing-Test-2026!xQ'
        )

        response = self.register(
            self.registration_data(email='EXISTING@EXAMPLE.COM')
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='Existing-Test-2026!xQ'
        )

        response = self.register(
            self.registration_data(username='existinguser')
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_username_with_different_casing_is_rejected(self):
        User.objects.create_user(
            username='existinguser',
            email='existing@example.com',
            password='Existing-Test-2026!xQ'
        )

        response = self.register(
            self.registration_data(username='EXISTINGUSER')
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_mismatch_is_rejected(self):
        response = self.register(
            self.registration_data(
                confirm_password='Different-Test-2026!xQ'
            )
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_is_rejected(self):
        response = self.register(
            self.registration_data(
                password='password',
                confirm_password='password'
            )
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_email_is_rejected(self):
        data = self.registration_data()
        data.pop('email')

        response = self.register(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_required_fields_are_rejected(self):
        response = self.register({})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(APITestCase):

    url = '/api/accounts/login/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='loginlearner',
            email='login@example.com',
            password='Vigil-Login-Test-2026!xQ',
            first_name='Login',
            last_name='Learner'
        )

        Profile.objects.create(
            user=self.user,
            role='LEARNER'
        )

    def login(self, email='login@example.com',
              password='Vigil-Login-Test-2026!xQ'):
        return self.client.post(
            self.url,
            {
                'email': email,
                'password': password
            },
            format='json'
        )

    def test_successful_login(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Login successful.')
        self.assertEqual(response.data['user']['email'], 'login@example.com')
        self.assertIn('sessionid', response.cookies)

    def test_login_with_different_email_casing(self):
        response = self.login(email='LOGIN@EXAMPLE.COM')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('sessionid', response.cookies)

    def test_incorrect_password_is_rejected(self):
        response = self.login(password='Wrong-Password-2026!xQ')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(response.data['non_field_errors'][0]),
            'Invalid email or password.'
        )

    def test_unknown_email_is_rejected(self):
        response = self.login(email='unknown@example.com')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            str(response.data['non_field_errors'][0]),
            'Invalid email or password.'
        )

    def test_inactive_account_cannot_login(self):
        self.user.is_active = False
        self.user.save()

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_email_is_rejected(self):
        response = self.client.post(
            self.url,
            {'password': 'Vigil-Login-Test-2026!xQ'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_password_is_rejected(self):
        response = self.client.post(
            self.url,
            {'email': 'login@example.com'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LogoutTests(APITestCase):

    url = '/api/accounts/logout/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='logoutlearner',
            email='logout@example.com',
            password='Vigil-Logout-Test-2026!xQ',
            first_name='Logout',
            last_name='Learner'
        )

        Profile.objects.create(
            user=self.user,
            role='LEARNER'
        )

    def test_successful_logout(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['message'],
            'Logout successful.'
        )
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_unauthenticated_user_cannot_logout(self):
        response = self.client.post(self.url, format='json')

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

class SessionFlowTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='sessionlearner',
            email='session@example.com',
            password='Vigil-Session-Test-2026!xQ',
            first_name='Session',
            last_name='Learner'
        )

        Profile.objects.create(
            user=self.user,
            role='LEARNER'
        )

    def test_complete_login_logout_session_flow(self):

        # 1. Log in using email and password
        login_response = self.client.post(
            '/api/accounts/login/',
            {
                'email': 'session@example.com',
                'password': 'Vigil-Session-Test-2026!xQ'
            },
            format='json'
        )

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        # 2. Confirm Django created an authenticated session
        self.assertIn('_auth_user_id', self.client.session)

        # 3. Access a protected endpoint while logged in
        user_response = self.client.get('/api/accounts/me/')

        self.assertEqual(user_response.status_code, status.HTTP_200_OK)
        self.assertEqual(user_response.data['email'], 'session@example.com')

        # 4. Log out
        logout_response = self.client.post(
            '/api/accounts/logout/',
            format='json'
        )

        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)

        # 5. Confirm the authenticated session has been cleared
        self.assertNotIn('_auth_user_id', self.client.session)

        # 6. Try accessing the protected endpoint again
        after_logout_response = self.client.get('/api/accounts/me/')

        self.assertEqual(
            after_logout_response.status_code,
            status.HTTP_403_FORBIDDEN
        )

class AccountDeletionRequestTests(APITestCase):

    url = '/api/accounts/deletion-request/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='deletelearner',
            email='delete@example.com',
            password='Vigil-Delete-Test-2026!xQ'
        )

        Profile.objects.create(
            user=self.user,
            role='LEARNER'
        )

        self.client.force_authenticate(user=self.user)

    def test_learner_can_request_deletion(self):
        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        deletion_request = AccountDeletionRequest.objects.get(
            user=self.user,
            status='PENDING'
        )

        self.assertEqual(deletion_request.role_at_request, 'LEARNER')

        actual_grace_period = (
            deletion_request.scheduled_deletion_at
            - deletion_request.requested_at
        )

        self.assertLess(
            abs((actual_grace_period - timedelta(days=15)).total_seconds()),
            1
        )

    def test_duplicate_pending_request_is_rejected(self):
        self.client.post(self.url, {}, format='json')

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.assertEqual(
            AccountDeletionRequest.objects.filter(
                user=self.user,
                status='PENDING'
            ).count(),
            1
        )

    def test_administrator_must_nominate_replacement(self):
        self.user.profile.role = 'ADMIN'
        self.user.profile.save()

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_administrator_deletion_has_30_day_grace_period(self):
        self.user.profile.role = 'ADMIN'
        self.user.profile.save()

        response = self.client.post(
            self.url,
            {'replacement_email': 'replacement@example.com'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        deletion_request = AccountDeletionRequest.objects.get(
            user=self.user
        )

        self.assertEqual(deletion_request.role_at_request, 'ADMIN')

        actual_grace_period = (
            deletion_request.scheduled_deletion_at
            - deletion_request.requested_at
        )

        self.assertLess(
            abs((actual_grace_period - timedelta(days=30)).total_seconds()),
            1
        )

    def test_administrator_cannot_nominate_own_email(self):
        self.user.profile.role = 'ADMIN'
        self.user.profile.save()

        response = self.client.post(
            self.url,
            {'replacement_email': 'DELETE@example.com'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_user_cannot_request_deletion(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

class AccountDeletionLoginTests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='deletionlogin',
            email='deletionlogin@example.com',
            password='Vigil-Delete-Login-2026!xQ'
        )

        Profile.objects.create(
            user=self.user,
            role='LEARNER'
        )

        self.deletion_request = AccountDeletionRequest.objects.create(
            user=self.user,
            role_at_request='LEARNER',
            scheduled_deletion_at=(
                timezone.now() + timedelta(days=15)
            )
        )

    def login(self, password='Vigil-Delete-Login-2026!xQ'):
        return self.client.post(
            '/api/accounts/login/',
            {
                'email': 'deletionlogin@example.com',
                'password': password
            },
            format='json'
        )

    def test_successful_login_cancels_pending_deletion(self):
        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.deletion_request.refresh_from_db()

        self.assertEqual(self.deletion_request.status, 'CANCELLED')
        self.assertIsNotNone(self.deletion_request.cancelled_at)

    def test_failed_login_does_not_cancel_deletion(self):
        response = self.login(password='Wrong-Password-2026!xQ')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.deletion_request.refresh_from_db()

        self.assertEqual(self.deletion_request.status, 'PENDING')
        self.assertIsNone(self.deletion_request.cancelled_at)

    def test_expired_deletion_cannot_be_cancelled_by_login(self):
        self.deletion_request.scheduled_deletion_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.deletion_request.save()

        response = self.login()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.deletion_request.refresh_from_db()

        self.assertEqual(self.deletion_request.status, 'PENDING')

    def test_existing_session_is_blocked_after_grace_period(self):
        login_response = self.login()

        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        self.assertIn('_auth_user_id', self.client.session)

        # Simulate the grace period expiring after login.
        self.deletion_request.scheduled_deletion_at = (
            timezone.now() - timedelta(minutes=1)
        )
        self.deletion_request.save()

        response = self.client.get('/api/accounts/me/')

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN
        )

    def test_replacement_login_confirms_administrator_access(self):

        replacement = User.objects.create_user(
            username='replacementlogin',
            email='replacementlogin@example.com',
            password='Vigil-Replacement-Login-2026!xQ'
        )

        Profile.objects.create(
            user=replacement,
            role='ADMIN'
        )

        self.deletion_request.role_at_request = 'ADMIN'
        self.deletion_request.replacement_email = ''
        self.deletion_request.replacement_user = replacement
        self.deletion_request.replacement_approved_at = timezone.now()
        self.deletion_request.save()

        response = self.client.post(
            '/api/accounts/login/',
            {
                'email': 'replacementlogin@example.com',
                'password': 'Vigil-Replacement-Login-2026!xQ'
            },
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.deletion_request.refresh_from_db()

        self.assertIsNotNone(
            self.deletion_request.replacement_confirmed_at
        )

class PermanentAccountDeletionTests(APITestCase):

    def create_learner(self):
        user = User.objects.create_user(
            username='permanentlearner',
            email='permanent@example.com',
            password='Vigil-Permanent-Test-2026!xQ'
        )

        Profile.objects.create(
            user=user,
            role='LEARNER'
        )

        return user

    def test_future_deletion_request_is_not_processed(self):
        user = self.create_learner()

        deletion_request = AccountDeletionRequest.objects.create(
            user=user,
            role_at_request='LEARNER',
            scheduled_deletion_at=(
                timezone.now() + timedelta(days=15)
            )
        )

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(User.objects.filter(pk=user.pk).exists())

        deletion_request.refresh_from_db()
        self.assertEqual(deletion_request.status, 'PENDING')

    def test_due_learner_account_is_permanently_deleted(self):
        user = self.create_learner()

        deletion_request = AccountDeletionRequest.objects.create(
            user=user,
            role_at_request='LEARNER',
            scheduled_deletion_at=(
                timezone.now() - timedelta(minutes=1)
            )
        )

        SecurityAuditLog.objects.create(
            actor=user,
            action='TEST_ACCOUNT_EVENT'
        )

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 1)

        self.assertFalse(User.objects.filter(pk=user.pk).exists())
        self.assertFalse(Profile.objects.filter(user_id=user.pk).exists())

        deletion_request.refresh_from_db()

        self.assertEqual(deletion_request.status, 'COMPLETED')
        self.assertIsNone(deletion_request.user_id)
        self.assertIsNotNone(deletion_request.completed_at)

        audit_event = SecurityAuditLog.objects.get(
            action='TEST_ACCOUNT_EVENT'
        )

        self.assertIsNone(audit_event.actor_id)

    def test_admin_deletion_waits_for_replacement_confirmation(self):
        old_admin = self.create_learner()
        old_admin.profile.role = 'ADMIN'
        old_admin.profile.save()

        AccountDeletionRequest.objects.create(
            user=old_admin,
            role_at_request='ADMIN',
            scheduled_deletion_at=(
                timezone.now() - timedelta(minutes=1)
            ),
            replacement_email='replacement@example.com'
        )

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(User.objects.filter(pk=old_admin.pk).exists())

    def test_admin_is_deleted_after_replacement_is_ready(self):
        old_admin = self.create_learner()
        old_admin.profile.role = 'ADMIN'
        old_admin.profile.save()

        replacement = User.objects.create_user(
            username='replacementadmin',
            email='replacement@example.com',
            password='Vigil-Replacement-Test-2026!xQ',
            is_staff=True,
        )

        Profile.objects.create(
            user=replacement,
            role='ADMIN'
        )

        now = timezone.now()

        deletion_request = AccountDeletionRequest.objects.create(
            user=old_admin,
            role_at_request='ADMIN',
            scheduled_deletion_at=now - timedelta(minutes=1),
            replacement_user=replacement,
            replacement_approved_at=now - timedelta(days=1),
            replacement_confirmed_at=now - timedelta(hours=1)
        )

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 1)
        self.assertFalse(User.objects.filter(pk=old_admin.pk).exists())

        deletion_request.refresh_from_db()

        self.assertEqual(deletion_request.status, 'COMPLETED')
        self.assertIsNone(deletion_request.user_id)


class AccountDeletionCooldownTests(APITestCase):

    url = '/api/accounts/deletion-request/'

    def setUp(self):
        self.user = User.objects.create_user(
            username='cooldownlearner',
            email='cooldown@example.com',
            password='Vigil-Cooldown-Test-2026!xQ'
        )

        Profile.objects.create(
            user=self.user,
            role='LEARNER'
        )

        self.client.force_authenticate(user=self.user)

    def create_cancelled_request(self, days_ago):
        now = timezone.now()

        return AccountDeletionRequest.objects.create(
            user=self.user,
            role_at_request='LEARNER',
            status='CANCELLED',
            requested_at=now - timedelta(days=20),
            scheduled_deletion_at=now - timedelta(days=5),
            cancelled_at=now - timedelta(days=days_ago)
        )

    def test_new_request_is_blocked_during_cooldown(self):
        self.create_cancelled_request(days_ago=9)

        response = self.client.post(
            self.url,
            {},
            format='json'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST
        )

    def test_new_request_is_allowed_after_cooldown(self):
        self.create_cancelled_request(days_ago=11)

        response = self.client.post(
            self.url,
            {},
            format='json'
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED
        )

class ProvisionAdminCommandTests(APITestCase):

    def setUp(self):
        self.old_admin = User.objects.create_user(
            username='oldadmin',
            email='oldadmin@example.com',
            password='Vigil-Old-Admin-2026!xQ'
        )

        Profile.objects.create(
            user=self.old_admin,
            role='ADMIN'
        )

        self.replacement = User.objects.create_user(
            username='newadmin',
            email='replacement@example.com',
            password='Vigil-New-Admin-2026!xQ'
        )

        Profile.objects.create(
            user=self.replacement,
            role='LEARNER'
        )

        self.deletion_request = AccountDeletionRequest.objects.create(
            user=self.old_admin,
            role_at_request='ADMIN',
            scheduled_deletion_at=timezone.now() + timedelta(days=30),
            replacement_email='replacement@example.com'
        )


    def test_existing_learner_is_promoted_to_administrator(self):

        output = StringIO()

        with patch(
            'builtins.input',
            side_effect=[
                str(self.deletion_request.pk),
                'Project Owner One',
                'Project Owner Two',
                'YES',
            ]
        ):
            call_command(
                'provision_admin',
                stdout=output
            )

        self.replacement.refresh_from_db()
        self.deletion_request.refresh_from_db()

        self.assertEqual(self.replacement.profile.role, 'ADMIN')

        # Vigil administrator role must not automatically
        # grant Django superuser privileges.
        self.assertTrue(self.replacement.is_staff)
        self.assertFalse(self.replacement.is_superuser)

        self.assertEqual(
            self.deletion_request.replacement_user_id,
            self.replacement.pk
        )

        self.assertEqual(self.deletion_request.replacement_email, '')

        self.assertIsNotNone(
            self.deletion_request.replacement_approved_at
        )

        self.assertEqual(
            SecurityAuditLog.objects.filter(
                action='ADMIN_REPLACEMENT_PROVISIONED'
            ).count(),
            1
        )


class AdministratorReplacementEdgeCaseTests(APITestCase):

    def create_admin(self, username, email):
        user = User.objects.create_user(
            username=username,
            email=email,
            password='Vigil-Edge-Test-2026!xQ',
            is_staff=True
        )

        Profile.objects.create(
            user=user,
            role='ADMIN'
        )

        return user

    def create_old_admin_request(self, old_admin, replacement):
        now = timezone.now()

        return AccountDeletionRequest.objects.create(
            user=old_admin,
            role_at_request='ADMIN',
            scheduled_deletion_at=now - timedelta(minutes=1),
            replacement_user=replacement,
            replacement_approved_at=now - timedelta(days=1),
            replacement_confirmed_at=now - timedelta(hours=1)
        )

    def test_replacement_without_staff_access_is_not_ready(self):
        old_admin = self.create_admin(
            'oldadmin_edge',
            'oldedge@example.com'
        )

        replacement = self.create_admin(
            'replacement_edge',
            'replacementedge@example.com'
        )

        replacement.is_staff = False
        replacement.save(update_fields=['is_staff'])

        deletion_request = self.create_old_admin_request(
            old_admin,
            replacement
        )

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(User.objects.filter(pk=old_admin.pk).exists())

    def test_superuser_cannot_be_used_as_replacement(self):
        old_admin = self.create_admin(
            'oldadmin_super',
            'oldsuper@example.com'
        )

        replacement = User.objects.create_superuser(
            username='replacement_super',
            email='replacementsuper@example.com',
            password='Vigil-Edge-Test-2026!xQ'
        )

        Profile.objects.create(
            user=replacement,
            role='ADMIN'
        )

        deletion_request = self.create_old_admin_request(
            old_admin,
            replacement
        )

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(User.objects.filter(pk=old_admin.pk).exists())

    def test_replacement_demoted_before_deletion_is_not_ready(self):
        old_admin = self.create_admin(
            'oldadmin_demote',
            'olddemote@example.com'
        )

        replacement = self.create_admin(
            'replacement_demote',
            'replacementdemote@example.com'
        )

        deletion_request = self.create_old_admin_request(
            old_admin,
            replacement
        )

        replacement.profile.role = 'LEARNER'
        replacement.profile.save(update_fields=['role'])

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(User.objects.filter(pk=old_admin.pk).exists())

    def test_replacement_with_pending_deletion_is_not_ready(self):
        old_admin = self.create_admin(
            'oldadmin_pending',
            'oldpending@example.com'
        )

        replacement = self.create_admin(
            'replacement_pending',
            'replacementpending@example.com'
        )

        AccountDeletionRequest.objects.create(
            user=replacement,
            role_at_request='ADMIN',
            scheduled_deletion_at=timezone.now() + timedelta(days=30),
            replacement_email='another@example.com'
        )

        self.create_old_admin_request(old_admin, replacement)

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(User.objects.filter(pk=old_admin.pk).exists())

    def test_changed_old_admin_role_prevents_automatic_deletion(self):
        old_admin = self.create_admin(
            'oldadmin_changed',
            'oldchanged@example.com'
        )

        replacement = self.create_admin(
            'replacement_changed',
            'replacementchanged@example.com'
        )

        self.create_old_admin_request(old_admin, replacement)

        old_admin.profile.role = 'LEARNER'
        old_admin.profile.save(update_fields=['role'])

        deleted_count = process_due_deletion_requests()

        self.assertEqual(deleted_count, 0)
        self.assertTrue(User.objects.filter(pk=old_admin.pk).exists())

# --------------------------------------------------
# Guest identity and session lifecycle tests
# --------------------------------------------------

class GuestIdentityAndSessionTests(APITestCase):

    def setUp(self):
        (
            self.identity,
            self.identity_token,
            self.guest_session,
            self.session_token,
        ) = create_guest_identity()

    def create_usage_record(self, identity=None):
        return GuestUsage.objects.create(
            guest_identity=identity or self.identity,
            usage_type='QUIZ',
            week_start=date(2026, 11, 16),
            used_count=3,
        )

    def test_guest_tokens_are_random_and_only_hashes_are_stored(self):
        another_token = generate_guest_token()

        self.assertNotEqual(self.identity_token, another_token)
        self.assertEqual(len(hash_guest_token(self.identity_token)), 64)

        self.assertEqual(
            self.identity.token_hash,
            hash_guest_token(self.identity_token),
        )
        self.assertNotEqual(
            self.identity.token_hash,
            self.identity_token,
        )
        self.assertEqual(
            self.guest_session.token_hash,
            hash_guest_token(self.session_token),
        )
        self.assertNotEqual(
            self.guest_session.token_hash,
            self.session_token,
        )

    def test_new_identity_and_session_have_expected_lifetimes(self):
        now = timezone.now()

        identity_lifetime = (
            self.identity.expires_at - now
        ).total_seconds()

        session_lifetime = (
            self.guest_session.expires_at - now
        ).total_seconds()

        self.assertAlmostEqual(
            identity_lifetime,
            GUEST_IDENTITY_LIFETIME_DAYS * 24 * 60 * 60,
            delta=2,
        )
        self.assertAlmostEqual(
            session_lifetime,
            GUEST_SESSION_LIFETIME_HOURS * 60 * 60,
            delta=2,
        )
        self.assertTrue(self.guest_session.is_active)

    def test_returning_guest_reuses_valid_identity_and_session(self):
        result = get_or_create_guest(
            self.identity_token,
            self.session_token,
        )

        identity, identity_token, guest_session, session_token = result

        self.assertEqual(identity.pk, self.identity.pk)
        self.assertEqual(identity_token, self.identity_token)
        self.assertEqual(guest_session.pk, self.guest_session.pk)
        self.assertEqual(session_token, self.session_token)

        self.assertEqual(GuestIdentity.objects.count(), 1)
        self.assertEqual(GuestSession.objects.count(), 1)

    def test_returning_guest_does_not_renew_identity_just_by_returning(self):
        original_expiry = self.identity.expires_at
        original_last_seen = self.identity.last_seen_at

        get_or_create_guest(
            self.identity_token,
            self.session_token,
        )

        self.identity.refresh_from_db()

        self.assertEqual(self.identity.expires_at, original_expiry)
        self.assertEqual(self.identity.last_seen_at, original_last_seen)

    def test_expired_session_gets_replaced_without_replacing_identity(self):
        usage = self.create_usage_record()

        self.guest_session.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.guest_session.save(update_fields=['expires_at'])

        (
            identity,
            identity_token,
            replacement_session,
            replacement_token,
        ) = get_or_create_guest(
            self.identity_token,
            self.session_token,
        )

        self.assertEqual(identity.pk, self.identity.pk)
        self.assertEqual(identity_token, self.identity_token)
        self.assertNotEqual(replacement_session.pk, self.guest_session.pk)
        self.assertNotEqual(replacement_token, self.session_token)

        self.guest_session.refresh_from_db()
        self.assertFalse(self.guest_session.is_active)

        self.assertTrue(replacement_session.is_active)
        self.assertEqual(replacement_session.guest_identity_id, self.identity.pk)
        self.assertTrue(GuestUsage.objects.filter(pk=usage.pk).exists())

    def test_missing_session_cookie_creates_new_session_for_valid_identity(self):
        (
            identity,
            identity_token,
            replacement_session,
            replacement_token,
        ) = get_or_create_guest(
            self.identity_token,
            None,
        )

        self.assertEqual(identity.pk, self.identity.pk)
        self.assertEqual(identity_token, self.identity_token)
        self.assertNotEqual(replacement_session.pk, self.guest_session.pk)
        self.assertNotEqual(replacement_token, self.session_token)

        self.guest_session.refresh_from_db()
        self.assertFalse(self.guest_session.is_active)

    def test_missing_identity_creates_new_identity_and_session(self):
        (
            new_identity,
            new_identity_token,
            new_session,
            new_session_token,
        ) = get_or_create_guest(None, None)

        self.assertNotEqual(new_identity.pk, self.identity.pk)
        self.assertNotEqual(new_identity_token, self.identity_token)
        self.assertNotEqual(new_session.pk, self.guest_session.pk)
        self.assertNotEqual(new_session_token, self.session_token)

        self.assertEqual(GuestIdentity.objects.count(), 2)

    def test_expired_identity_is_deleted_and_replaced(self):
        usage = self.create_usage_record()
        old_identity_id = self.identity.pk

        self.identity.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.identity.save(update_fields=['expires_at'])

        (
            new_identity,
            new_identity_token,
            new_session,
            new_session_token,
        ) = get_or_create_guest(
            self.identity_token,
            self.session_token,
        )

        self.assertNotEqual(new_identity.pk, old_identity_id)
        self.assertNotEqual(new_identity_token, self.identity_token)
        self.assertNotEqual(new_session_token, self.session_token)

        self.assertFalse(
            GuestIdentity.objects.filter(pk=old_identity_id).exists()
        )
        self.assertFalse(
            GuestSession.objects.filter(
                guest_identity_id=old_identity_id
            ).exists()
        )
        self.assertFalse(GuestUsage.objects.filter(pk=usage.pk).exists())

    def test_create_new_session_deactivates_previous_active_session(self):
        new_session, new_token = create_guest_session(self.identity)

        self.guest_session.refresh_from_db()

        self.assertFalse(self.guest_session.is_active)
        self.assertTrue(new_session.is_active)
        self.assertNotEqual(new_session.pk, self.guest_session.pk)
        self.assertEqual(
            new_session.token_hash,
            hash_guest_token(new_token),
        )

        self.assertEqual(
            GuestSession.objects.filter(
                guest_identity=self.identity,
                is_active=True,
            ).count(),
            1,
        )

    def test_session_validation_accepts_valid_tokens(self):
        result = validate_guest_session(
            self.identity_token,
            self.session_token,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.guest_session.pk)

    def test_session_validation_rejects_missing_tokens(self):
        self.assertIsNone(
            validate_guest_session(None, self.session_token)
        )
        self.assertIsNone(
            validate_guest_session(self.identity_token, None)
        )
        self.assertIsNone(
            validate_guest_session(None, None)
        )

    def test_session_validation_rejects_incorrect_tokens(self):
        self.assertIsNone(
            validate_guest_session(
                'incorrect-identity-token',
                self.session_token,
            )
        )
        self.assertIsNone(
            validate_guest_session(
                self.identity_token,
                'incorrect-session-token',
            )
        )

    def test_session_validation_rejects_expired_session(self):
        self.guest_session.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.guest_session.save(update_fields=['expires_at'])

        self.assertIsNone(
            validate_guest_session(
                self.identity_token,
                self.session_token,
            )
        )

    def test_session_validation_rejects_inactive_session(self):
        self.guest_session.is_active = False
        self.guest_session.save(update_fields=['is_active'])

        self.assertIsNone(
            validate_guest_session(
                self.identity_token,
                self.session_token,
            )
        )

    def test_session_validation_rejects_expired_identity(self):
        self.identity.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.identity.save(update_fields=['expires_at'])

        self.assertIsNone(
            validate_guest_session(
                self.identity_token,
                self.session_token,
            )
        )

    def test_validation_does_not_renew_identity_or_activity_timestamps(self):
        original_expiry = self.identity.expires_at
        original_identity_activity = self.identity.last_seen_at
        original_session_activity = self.guest_session.last_seen_at

        result = validate_guest_session(
            self.identity_token,
            self.session_token,
        )

        self.assertIsNotNone(result)

        self.identity.refresh_from_db()
        self.guest_session.refresh_from_db()

        self.assertEqual(self.identity.expires_at, original_expiry)
        self.assertEqual(
            self.identity.last_seen_at,
            original_identity_activity,
        )
        self.assertEqual(
            self.guest_session.last_seen_at,
            original_session_activity,
        )

    def test_meaningful_activity_renews_identity_lifetime(self):
        old_expiry = timezone.now() + timedelta(days=5)

        self.identity.expires_at = old_expiry
        self.identity.save(update_fields=['expires_at'])

        validated_session = validate_guest_session(
            self.identity_token,
            self.session_token,
        )

        result = record_guest_activity(validated_session)

        self.assertTrue(result)

        self.identity.refresh_from_db()
        self.guest_session.refresh_from_db()

        expected_expiry = (
            timezone.now() + timedelta(days=GUEST_IDENTITY_LIFETIME_DAYS)
        )

        self.assertGreater(self.identity.expires_at, old_expiry)
        self.assertAlmostEqual(
            self.identity.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=2,
        )
        self.assertGreaterEqual(
            self.identity.last_seen_at,
            self.guest_session.created_at,
        )
        self.assertGreaterEqual(
            self.guest_session.last_seen_at,
            self.guest_session.created_at,
        )

    def test_record_activity_does_not_extend_24_hour_session_expiry(self):
        original_session_expiry = self.guest_session.expires_at

        validated_session = validate_guest_session(
            self.identity_token,
            self.session_token,
        )

        self.assertTrue(record_guest_activity(validated_session))

        self.guest_session.refresh_from_db()

        self.assertEqual(
            self.guest_session.expires_at,
            original_session_expiry,
        )

    def test_record_activity_rejects_none(self):
        self.assertFalse(record_guest_activity(None))

    def test_record_activity_rejects_inactive_session(self):
        validated_session = validate_guest_session(
            self.identity_token,
            self.session_token,
        )

        self.guest_session.is_active = False
        self.guest_session.save(update_fields=['is_active'])

        old_expiry = self.identity.expires_at

        self.assertFalse(record_guest_activity(validated_session))

        self.identity.refresh_from_db()
        self.assertEqual(self.identity.expires_at, old_expiry)

    def test_record_activity_rejects_expired_session(self):
        validated_session = validate_guest_session(
            self.identity_token,
            self.session_token,
        )

        self.guest_session.expires_at = (
            timezone.now() - timedelta(seconds=1)
        )
        self.guest_session.save(update_fields=['expires_at'])

        old_expiry = self.identity.expires_at

        self.assertFalse(record_guest_activity(validated_session))

        self.identity.refresh_from_db()
        self.assertEqual(self.identity.expires_at, old_expiry)

    def test_end_session_invalidates_session_but_preserves_identity_and_usage(self):
        usage = self.create_usage_record()

        result = end_guest_session(
            self.identity_token,
            self.session_token,
        )

        self.assertTrue(result)

        self.guest_session.refresh_from_db()
        self.identity.refresh_from_db()

        self.assertFalse(self.guest_session.is_active)
        self.assertTrue(
            GuestIdentity.objects.filter(pk=self.identity.pk).exists()
        )
        self.assertTrue(GuestUsage.objects.filter(pk=usage.pk).exists())

    def test_end_session_rejects_incorrect_tokens(self):
        result = end_guest_session(
            self.identity_token,
            'incorrect-session-token',
        )

        self.assertFalse(result)

        self.guest_session.refresh_from_db()
        self.assertTrue(self.guest_session.is_active)

    def test_end_session_rejects_missing_tokens(self):
        self.assertFalse(end_guest_session(None, self.session_token))
        self.assertFalse(end_guest_session(self.identity_token, None))


class GuestWeeklyPeriodTests(APITestCase):

    def test_week_starts_on_monday_in_india_timezone(self):
        india = ZoneInfo('Asia/Kolkata')

        sunday_night = datetime(
            2026, 11, 22, 23, 59, 59,
            tzinfo=india,
        )
        monday_midnight = datetime(
            2026, 11, 23, 0, 0, 0,
            tzinfo=india,
        )

        self.assertEqual(
            get_current_guest_week_start(sunday_night),
            date(2026, 11, 16),
        )
        self.assertEqual(
            get_current_guest_week_start(monday_midnight),
            date(2026, 11, 23),
        )

    def test_week_start_uses_india_date_for_utc_timestamp(self):
        # 2026-11-22 18:30 UTC is 2026-11-23 00:00 in India.
        utc_timestamp = datetime(
            2026, 11, 22, 18, 30, 0,
            tzinfo=ZoneInfo('UTC'),
        )

        self.assertEqual(
            get_current_guest_week_start(utc_timestamp),
            date(2026, 11, 23),
        )


class GuestSessionEndpointTests(APITestCase):

    url = '/api/accounts/guest-session/'

    def test_first_guest_session_request_sets_both_cookies(self):
        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['guest'])

        self.assertIn(GUEST_IDENTITY_COOKIE, response.cookies)
        self.assertIn(GUEST_SESSION_COOKIE, response.cookies)

        identity_cookie = response.cookies[GUEST_IDENTITY_COOKIE]
        session_cookie = response.cookies[GUEST_SESSION_COOKIE]

        self.assertTrue(identity_cookie['httponly'])
        self.assertTrue(session_cookie['httponly'])
        self.assertEqual(identity_cookie['samesite'], 'Lax')
        self.assertEqual(session_cookie['samesite'], 'Lax')

        self.assertEqual(GuestIdentity.objects.count(), 1)
        self.assertEqual(GuestSession.objects.count(), 1)

    def test_guest_session_endpoint_reuses_cookies_on_return(self):
        first_response = self.client.post(self.url, {}, format='json')

        identity_token = first_response.cookies[
            GUEST_IDENTITY_COOKIE
        ].value
        session_token = first_response.cookies[
            GUEST_SESSION_COOKIE
        ].value

        self.client.cookies[GUEST_IDENTITY_COOKIE] = identity_token
        self.client.cookies[GUEST_SESSION_COOKIE] = session_token

        second_response = self.client.post(self.url, {}, format='json')

        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(GuestIdentity.objects.count(), 1)
        self.assertEqual(GuestSession.objects.count(), 1)

        self.assertEqual(
            second_response.cookies[GUEST_IDENTITY_COOKIE].value,
            identity_token,
        )
        self.assertEqual(
            second_response.cookies[GUEST_SESSION_COOKIE].value,
            session_token,
        )

    def test_guest_session_endpoint_creates_new_session_after_expiry(self):
        first_response = self.client.post(self.url, {}, format='json')

        identity_token = first_response.cookies[
            GUEST_IDENTITY_COOKIE
        ].value
        old_session_token = first_response.cookies[
            GUEST_SESSION_COOKIE
        ].value

        old_session = GuestSession.objects.get(
            token_hash=hash_guest_token(old_session_token)
        )
        old_session.expires_at = timezone.now() - timedelta(seconds=1)
        old_session.save(update_fields=['expires_at'])

        self.client.cookies[GUEST_IDENTITY_COOKIE] = identity_token
        self.client.cookies[GUEST_SESSION_COOKIE] = old_session_token

        response = self.client.post(self.url, {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(GuestIdentity.objects.count(), 1)
        self.assertEqual(GuestSession.objects.count(), 2)

        self.assertNotEqual(
            response.cookies[GUEST_SESSION_COOKIE].value,
            old_session_token,
        )

        old_session.refresh_from_db()
        self.assertFalse(old_session.is_active)


class GuestAuthenticationTransitionTests(APITestCase):

    def setUp(self):
        (
            self.identity,
            self.identity_token,
            self.guest_session,
            self.session_token,
        ) = create_guest_identity()

        self.client.cookies[GUEST_IDENTITY_COOKIE] = self.identity_token
        self.client.cookies[GUEST_SESSION_COOKIE] = self.session_token

    def assert_guest_cookies_cleared(self, response):
        self.assertIn(GUEST_IDENTITY_COOKIE, response.cookies)
        self.assertIn(GUEST_SESSION_COOKIE, response.cookies)

        self.assertEqual(
            int(response.cookies[GUEST_IDENTITY_COOKIE]['max-age']),
            0,
        )
        self.assertEqual(
            int(response.cookies[GUEST_SESSION_COOKIE]['max-age']),
            0,
        )

    def test_registration_ends_guest_session_and_clears_guest_cookies(self):
        response = self.client.post(
            '/api/accounts/register/',
            {
                'first_name': 'New',
                'last_name': 'Learner',
                'username': 'guestconverted',
                'email': 'guestconverted@example.com',
                'password': 'Vigil-Guest-Test-2026!xQ',
                'confirm_password': 'Vigil-Guest-Test-2026!xQ',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_guest_cookies_cleared(response)

        self.guest_session.refresh_from_db()
        self.assertFalse(self.guest_session.is_active)

        self.assertTrue(
            GuestIdentity.objects.filter(pk=self.identity.pk).exists()
        )

    def test_successful_login_ends_guest_session_and_clears_guest_cookies(self):
        user = User.objects.create_user(
            username='guestlogin',
            email='guestlogin@example.com',
            password='Vigil-Guest-Login-2026!xQ',
        )
        Profile.objects.create(user=user, role='LEARNER')

        response = self.client.post(
            '/api/accounts/login/',
            {
                'email': 'guestlogin@example.com',
                'password': 'Vigil-Guest-Login-2026!xQ',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assert_guest_cookies_cleared(response)

        self.guest_session.refresh_from_db()
        self.assertFalse(self.guest_session.is_active)

        self.assertTrue(
            GuestIdentity.objects.filter(pk=self.identity.pk).exists()
        )

    def test_failed_login_does_not_end_guest_session(self):
        user = User.objects.create_user(
            username='guestfailedlogin',
            email='guestfailed@example.com',
            password='Vigil-Guest-Login-2026!xQ',
        )
        Profile.objects.create(user=user, role='LEARNER')

        response = self.client.post(
            '/api/accounts/login/',
            {
                'email': 'guestfailed@example.com',
                'password': 'Incorrect-Password-2026!xQ',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        self.guest_session.refresh_from_db()
        self.assertTrue(self.guest_session.is_active)
