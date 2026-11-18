from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase
from datetime import timedelta

from django.utils import timezone

from .models import (
    Profile,
    AccountDeletionRequest,
    SecurityAuditLog,
)
from .services import process_due_deletion_requests

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
