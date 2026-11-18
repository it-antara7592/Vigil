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
)


def handle_service_validation_error(error):
    """
    Convert Django validation errors into DRF API errors.
    """

    if hasattr(error, 'message_dict'):
        raise ValidationError(error.message_dict)

    raise ValidationError(error.messages)


class RegistrationView(generics.CreateAPIView):

    serializer_class = RegistrationSerializer
    permission_classes = [AllowAny]


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

        return Response(
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
