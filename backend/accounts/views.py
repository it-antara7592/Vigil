
from django.conf import settings
from django.contrib.auth import login, logout
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError

from .serializers import (
    RegistrationSerializer,
    LoginSerializer,
    AccountDeletionRequestSerializer,
)

from .models import AccountDeletionRequest

from .services import (
    create_deletion_request,
    cancel_pending_deletion_on_login,
    confirm_administrator_replacement_login,
    record_audit_event,
    get_or_create_guest,
    end_guest_session,
    GUEST_IDENTITY_COOKIE,
    GUEST_SESSION_COOKIE,
    GUEST_IDENTITY_LIFETIME_DAYS,
    GUEST_SESSION_LIFETIME_HOURS,
)


def handle_service_validation_error(error):
    """
    Convert Django validation errors into DRF API errors.
    """

    if hasattr(error, 'message_dict'):
        raise ValidationError(error.message_dict)

    raise ValidationError(error.messages)


def clear_guest_cookies(request, response):
    """
    Invalidate the current guest session and clear both guest cookies.

    The guest identity and its usage records are retained until
    the identity's normal expiry.
    """

    identity_token = request.COOKIES.get(GUEST_IDENTITY_COOKIE)
    session_token = request.COOKIES.get(GUEST_SESSION_COOKIE)

    end_guest_session(
        identity_token=identity_token,
        session_token=session_token,
    )

    response.delete_cookie(
        GUEST_IDENTITY_COOKIE,
        path='/',
        samesite='Lax',
    )

    response.delete_cookie(
        GUEST_SESSION_COOKIE,
        path='/',
        samesite='Lax',
    )

    return response


def set_guest_cookies(response, identity_token, session_token):
    """
    Set the persistent guest identity cookie and temporary
    guest session cookie.
    """

    secure_cookie = not settings.DEBUG

    response.set_cookie(
        key=GUEST_IDENTITY_COOKIE,
        value=identity_token,
        max_age=GUEST_IDENTITY_LIFETIME_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=secure_cookie,
        samesite='Lax',
        path='/',
    )

    response.set_cookie(
        key=GUEST_SESSION_COOKIE,
        value=session_token,
        max_age=GUEST_SESSION_LIFETIME_HOURS * 60 * 60,
        httponly=True,
        secure=secure_cookie,
        samesite='Lax',
        path='/',
    )

    return response


class GuestSessionView(APIView):
    """
    Create or renew a guest identity/session using the cookies
    already present in the browser.
    """

    permission_classes = [AllowAny]

    def post(self, request):

        identity_token = request.COOKIES.get(GUEST_IDENTITY_COOKIE)
        session_token = request.COOKIES.get(GUEST_SESSION_COOKIE)

        (
            guest_identity,
            raw_identity_token,
            guest_session,
            raw_session_token,
        ) = get_or_create_guest(
            identity_token=identity_token,
            session_token=session_token,
        )

        response = Response(
            {
                "message": "Guest session is ready.",
                "guest": True,
                "identity_expires_at": guest_identity.expires_at,
                "session_expires_at": guest_session.expires_at,
            },
            status=status.HTTP_200_OK,
        )

        return set_guest_cookies(
            response,
            raw_identity_token,
            raw_session_token,
        )


class RegistrationView(generics.CreateAPIView):

    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):

        response = super().create(request, *args, **kwargs)

        return clear_guest_cookies(request, response)


class LoginView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        serializer = LoginSerializer(
            data=request.data,
            context={'request': request}
        )

        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data['user']

        try:
            # A successful login automatically cancels a pending
            # deletion request if it is still within the grace period.
            cancel_pending_deletion_on_login(user)

        except DjangoValidationError as error:
            handle_service_validation_error(error)

        login(request, user)

        confirm_administrator_replacement_login(user)

        record_audit_event(
            action='USER_LOGIN_SUCCESSFUL',
            actor=user,
            target_type='User',
            target_id=user.pk
        )

        response = Response(
            {
                "message": "Login successful.",
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "username": user.username,
                    "email": user.email,
                    "role": user.profile.role,
                }
            },
            status=status.HTTP_200_OK
        )

        return clear_guest_cookies(request, response)


class LogoutView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        user = request.user

        record_audit_event(
            action='USER_LOGOUT',
            actor=user,
            target_type='User',
            target_id=user.pk
        )

        logout(request)

        return Response(
            {
                "message": "Logout successful."
            },
            status=status.HTTP_200_OK
        )


class CurrentUserView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        return Response({
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "username": user.username,
            "email": user.email,
            "role": user.profile.role,
        })


class AccountDeletionView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Return the current user's pending deletion request, if any.
        """

        deletion_request = AccountDeletionRequest.objects.filter(
            user=request.user,
            status='PENDING'
        ).first()

        if deletion_request is None:
            return Response({
                "has_pending_deletion": False
            })

        return Response({
            "has_pending_deletion": True,
            "status": deletion_request.status,
            "role": deletion_request.role_at_request,
            "requested_at": deletion_request.requested_at,
            "scheduled_deletion_at": (
                deletion_request.scheduled_deletion_at
            ),
        })

    def post(self, request):
        """
        Submit an account deletion request.
        """

        serializer = AccountDeletionRequestSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        try:
            deletion_request = create_deletion_request(
                user=request.user,
                replacement_email=serializer.validated_data.get(
                    'replacement_email'
                )
            )

        except DjangoValidationError as error:
            handle_service_validation_error(error)

        return Response(
            {
                "message": "Account deletion request submitted.",
                "deletion_request": {
                    "id": deletion_request.pk,
                    "status": deletion_request.status,
                    "role": deletion_request.role_at_request,
                    "requested_at": deletion_request.requested_at,
                    "scheduled_deletion_at": (
                        deletion_request.scheduled_deletion_at
                    ),
                }
            },
            status=status.HTTP_201_CREATED
        )
