from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone

from .models import AccountDeletionRequest

User = get_user_model()

class EmailAuthenticationBackend(ModelBackend):

    def account_deletion_expired(self, user):
        """
        Check whether the user's pending account deletion
        has passed its scheduled deletion time.
        """

        return AccountDeletionRequest.objects.filter(
            user=user,
            status='PENDING',
            scheduled_deletion_at__lte=timezone.now()
        ).exists()

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs
    ):

        email = kwargs.get('email', username)

        if email is None or password is None:
            return None

        try:
            user = User.objects.get(
                email__iexact=email.strip()
            )

        except User.DoesNotExist:
            return None

        except User.MultipleObjectsReturned:
            return None

        if not user.check_password(password):
            return None

        if not self.user_can_authenticate(user):
            return None

        # An expired pending deletion cannot be recovered by login.
        if self.account_deletion_expired(user):
            return None

        return user

    def get_user(self, user_id):
        """
        Validate an existing session when Django retrieves
        its authenticated user.
        """

        try:
            user = User.objects.get(pk=user_id)

        except User.DoesNotExist:
            return None

        if not self.user_can_authenticate(user):
            return None

        if self.account_deletion_expired(user):
            return None

        return user
