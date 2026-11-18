from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

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