
import hashlib
import secrets

from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    AccountDeletionRequest,
    SecurityAuditLog,
    Profile,
    GuestIdentity,
    GuestSession,
)


User = get_user_model()


# Account deletion settings
LEARNER_GRACE_PERIOD_DAYS = 15
ADMIN_GRACE_PERIOD_DAYS = 30
DELETION_COOLDOWN_DAYS = 10


# Guest lifecycle settings
GUEST_IDENTITY_LIFETIME_DAYS = 60
GUEST_SESSION_LIFETIME_HOURS = 24

GUEST_IDENTITY_COOKIE = 'vigil_guest_identity'
GUEST_SESSION_COOKIE = 'vigil_guest_session'

INDIA_TIMEZONE = ZoneInfo('Asia/Kolkata')


# --------------------------------------------------
# Audit events
# --------------------------------------------------

def record_audit_event(
    action,
    actor=None,
    target_type='',
    target_id='',
    metadata=None
):
    """
    Record an important security or administrative event.
    """

    return SecurityAuditLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else '',
        metadata=metadata or {}
    )


# --------------------------------------------------
# Guest token helpers
# --------------------------------------------------

def generate_guest_token():
    """
    Generate a cryptographically secure guest token.
    """

    return secrets.token_urlsafe(32)


def hash_guest_token(token):
    """
    Return the SHA-256 hash of a guest token.

    Only token hashes are stored in the database.
    """

    return hashlib.sha256(
        token.encode('utf-8')
    ).hexdigest()


# --------------------------------------------------
# Guest identity and session creation
# --------------------------------------------------

@transaction.atomic
def create_guest_session(guest_identity):
    """
    Create a new 24-hour session for an existing guest identity.

    Any previous active session for the identity is deactivated.
    """

    locked_identity = (
        GuestIdentity.objects
        .select_for_update()
        .get(pk=guest_identity.pk)
    )

    now = timezone.now()

    if locked_identity.expires_at <= now:
        raise ValidationError(
            "Guest identity has expired."
        )

    GuestSession.objects.filter(
        guest_identity=locked_identity,
        is_active=True
    ).update(is_active=False)

    raw_token = generate_guest_token()

    guest_session = GuestSession.objects.create(
        guest_identity=locked_identity,
        token_hash=hash_guest_token(raw_token),
        expires_at=now + timedelta(
            hours=GUEST_SESSION_LIFETIME_HOURS
        )
    )

    return guest_session, raw_token


@transaction.atomic
def create_guest_identity():
    """
    Create a new guest identity and its first session.

    Returns:
        guest_identity,
        raw_identity_token,
        guest_session,
        raw_session_token
    """

    now = timezone.now()

    raw_identity_token = generate_guest_token()

    guest_identity = GuestIdentity.objects.create(
        token_hash=hash_guest_token(raw_identity_token),
        expires_at=now + timedelta(
            days=GUEST_IDENTITY_LIFETIME_DAYS
        )
    )

    guest_session, raw_session_token = create_guest_session(
        guest_identity
    )

    return (
        guest_identity,
        raw_identity_token,
        guest_session,
        raw_session_token
    )


# --------------------------------------------------
# Returning guest recognition
# --------------------------------------------------

@transaction.atomic
def get_or_create_guest(
    identity_token=None,
    session_token=None
):
    """
    Recognise a returning guest or create a new guest identity.

    A valid identity retains its usage records when its
    24-hour session expires.

    This function does not renew the 60-day identity lifetime.
    Identity renewal happens only through record_guest_activity().

    Returns:
        guest_identity,
        raw_identity_token,
        guest_session,
        raw_session_token
    """

    now = timezone.now()

    guest_identity = None

    if identity_token:
        guest_identity = (
            GuestIdentity.objects
            .select_for_update()
            .filter(
                token_hash=hash_guest_token(identity_token)
            )
            .first()
        )

    # Remove an expired identity and its associated records.
    if guest_identity and guest_identity.expires_at <= now:
        guest_identity.delete()
        guest_identity = None

    # Create a new identity if none exists.
    if guest_identity is None:
        return create_guest_identity()

    raw_identity_token = identity_token

    # Check whether the existing session is valid.
    guest_session = None

    if session_token:
        guest_session = (
            GuestSession.objects
            .select_for_update()
            .filter(
                guest_identity=guest_identity,
                token_hash=hash_guest_token(session_token),
                is_active=True,
                expires_at__gt=now
            )
            .first()
        )

    # Reuse the existing valid session.
    if guest_session:
        return (
            guest_identity,
            raw_identity_token,
            guest_session,
            session_token
        )

    # Deactivate expired sessions.
    GuestSession.objects.filter(
        guest_identity=guest_identity,
        is_active=True,
        expires_at__lte=now
    ).update(is_active=False)

    # Create a replacement session while preserving the identity.
    guest_session, raw_session_token = create_guest_session(
        guest_identity
    )

    return (
        guest_identity,
        raw_identity_token,
        guest_session,
        raw_session_token
    )


# --------------------------------------------------
# Guest session validation
# --------------------------------------------------

def validate_guest_session(
    identity_token,
    session_token
):
    """
    Verify that the identity and session tokens are valid.

    Validation alone does not renew the identity lifetime
    or update activity timestamps.

    Returns the GuestSession if valid, otherwise None.
    """

    if not identity_token or not session_token:
        return None

    now = timezone.now()

    guest_session = (
        GuestSession.objects
        .select_related('guest_identity')
        .filter(
            guest_identity__token_hash=hash_guest_token(
                identity_token
            ),
            guest_identity__expires_at__gt=now,
            token_hash=hash_guest_token(session_token),
            expires_at__gt=now,
            is_active=True
        )
        .first()
    )

    return guest_session


# --------------------------------------------------
# Meaningful guest activity
# --------------------------------------------------

@transaction.atomic
def record_guest_activity(guest_session):
    """
    Record meaningful activity from a validated guest session.

    Renew the guest identity's 60-day inactivity period and
    update the identity and session activity timestamps.

    Returns True if activity was recorded, otherwise False.

    Call this only for meaningful actions, such as:
    - Opening or actively reading a lesson.
    - Starting or participating in a quiz.
    - Starting or participating in a simulation.

    Do not call it for background requests, routine session
    validation or ordinary landing-page browsing.
    """

    if guest_session is None:
        return False

    now = timezone.now()

    # Lock the identity first to keep the same lock order
    # used by guest session creation.
    guest_identity = (
        GuestIdentity.objects
        .select_for_update()
        .filter(
            pk=guest_session.guest_identity_id,
            expires_at__gt=now
        )
        .first()
    )

    if guest_identity is None:
        return False

    # Recheck the session while holding the identity lock.
    locked_session = (
        GuestSession.objects
        .select_for_update()
        .filter(
            pk=guest_session.pk,
            guest_identity=guest_identity,
            is_active=True,
            expires_at__gt=now
        )
        .first()
    )

    if locked_session is None:
        return False

    guest_identity.expires_at = now + timedelta(
        days=GUEST_IDENTITY_LIFETIME_DAYS
    )

    guest_identity.save(
        update_fields=[
            'expires_at',
            'last_seen_at'
        ]
    )

    locked_session.last_seen_at = now

    locked_session.save(
        update_fields=['last_seen_at']
    )

    return True


# --------------------------------------------------
# Guest weekly period
# --------------------------------------------------

def get_current_guest_week_start(now=None):
    """
    Return the Monday date for the current guest usage week.

    The week begins Monday at 00:00 in Asia/Kolkata time.

    The returned value is a date, not a datetime.
    """

    if now is None:
        now = timezone.now()

    india_now = now.astimezone(INDIA_TIMEZONE)

    return (
        india_now.date()
        - timedelta(days=india_now.weekday())
    )


# --------------------------------------------------
# Guest session invalidation
# --------------------------------------------------

@transaction.atomic
def end_guest_session(
    identity_token=None,
    session_token=None
):
    """
    Invalidate the current guest session when a visitor
    registers or logs in.

    The guest identity and its usage records are preserved.
    """

    if not identity_token or not session_token:
        return False

    guest_identity = (
        GuestIdentity.objects
        .select_for_update()
        .filter(
            token_hash=hash_guest_token(identity_token)
        )
        .first()
    )

    if guest_identity is None:
        return False

    guest_session = (
        GuestSession.objects
        .select_for_update()
        .filter(
            guest_identity=guest_identity,
            token_hash=hash_guest_token(session_token),
            is_active=True
        )
        .first()
    )

    if guest_session is None:
        return False

    guest_session.is_active = False

    guest_session.save(
        update_fields=['is_active']
    )

    return True


# --------------------------------------------------
# Account deletion
# --------------------------------------------------

@transaction.atomic
def create_deletion_request(user, replacement_email=None):
    """
    Create an account deletion request.

    Learners receive a 15-day grace period.
    Administrators receive a 30-day grace period and
    must nominate a replacement administrator.
    """

    locked_user = User.objects.select_for_update().get(pk=user.pk)

    if not locked_user.is_active:
        raise ValidationError(
            "Inactive accounts cannot request deletion."
        )

    try:
        role = locked_user.profile.role
    except Profile.DoesNotExist:
        raise ValidationError(
            "The account does not have a valid profile."
        )

    if role not in ('LEARNER', 'ADMIN'):
        raise ValidationError("Invalid account role.")

    if AccountDeletionRequest.objects.filter(
        user=locked_user,
        status='PENDING'
    ).exists():
        raise ValidationError(
            "A deletion request is already pending."
        )

    last_cancelled = AccountDeletionRequest.objects.filter(
        user=locked_user,
        status='CANCELLED',
        cancelled_at__isnull=False
    ).order_by('-cancelled_at').first()

    now = timezone.now()

    if last_cancelled:
        cooldown_ends_at = (
            last_cancelled.cancelled_at
            + timedelta(days=DELETION_COOLDOWN_DAYS)
        )

        if now < cooldown_ends_at:
            raise ValidationError({
                "cooldown": (
                    "You cannot request deletion again until "
                    f"{cooldown_ends_at.isoformat()}."
                )
            })

    if role == 'ADMIN':
        if not replacement_email or not replacement_email.strip():
            raise ValidationError({
                "replacement_email": (
                    "A replacement administrator must be nominated."
                )
            })

        replacement_email = replacement_email.strip().lower()

        if replacement_email == locked_user.email.strip().lower():
            raise ValidationError({
                "replacement_email": (
                    "You cannot nominate your own account."
                )
            })
    else:
        replacement_email = ''

    grace_period = (
        ADMIN_GRACE_PERIOD_DAYS
        if role == 'ADMIN'
        else LEARNER_GRACE_PERIOD_DAYS
    )

    deletion_request = AccountDeletionRequest.objects.create(
        user=locked_user,
        role_at_request=role,
        scheduled_deletion_at=now + timedelta(days=grace_period),
        replacement_email=replacement_email
    )

    record_audit_event(
        action='ACCOUNT_DELETION_REQUESTED',
        actor=locked_user,
        target_type='AccountDeletionRequest',
        target_id=deletion_request.pk,
        metadata={
            'role': role,
            'grace_period_days': grace_period,
        }
    )

    return deletion_request


@transaction.atomic
def cancel_pending_deletion_on_login(user):
    """
    Automatically cancel a pending deletion request after
    a successful login within the grace period.

    Returns True if a pending request was cancelled.
    Returns False if there was no pending request.
    """

    locked_user = User.objects.select_for_update().get(pk=user.pk)

    deletion_request = (
        AccountDeletionRequest.objects
        .select_for_update()
        .filter(
            user=locked_user,
            status='PENDING'
        )
        .first()
    )

    if deletion_request is None:
        return False

    now = timezone.now()

    if deletion_request.scheduled_deletion_at <= now:
        raise ValidationError(
            "The account deletion grace period has expired."
        )

    deletion_request.status = 'CANCELLED'
    deletion_request.cancelled_at = now

    # The nomination is no longer needed after cancellation.
    deletion_request.replacement_email = ''
    deletion_request.replacement_user = None
    deletion_request.replacement_approved_at = None
    deletion_request.replacement_confirmed_at = None

    deletion_request.save(
        update_fields=[
            'status',
            'cancelled_at',
            'replacement_email',
            'replacement_user',
            'replacement_approved_at',
            'replacement_confirmed_at',
        ]
    )

    record_audit_event(
        action='ACCOUNT_DELETION_CANCELLED',
        actor=locked_user,
        target_type='AccountDeletionRequest',
        target_id=deletion_request.pk,
        metadata={
            'role': deletion_request.role_at_request,
            'reason': 'Successful login during grace period',
        }
    )

    return True


def administrator_replacement_is_ready(deletion_request):
    """
    Check whether the nominated replacement is currently
    eligible to take over administrator access.
    """

    replacement = deletion_request.replacement_user

    if not replacement:
        return False

    if not replacement.is_active:
        return False

    if replacement.is_superuser:
        return False

    if not replacement.is_staff:
        return False

    try:
        profile = replacement.profile
    except Profile.DoesNotExist:
        return False

    if profile.role != 'ADMIN':
        return False

    if replacement.pk == deletion_request.user_id:
        return False

    if AccountDeletionRequest.objects.filter(
        user=replacement,
        status='PENDING'
    ).exists():
        return False

    if deletion_request.replacement_approved_at is None:
        return False

    if deletion_request.replacement_confirmed_at is None:
        return False

    return True


def process_due_deletion_requests():
    """
    Permanently delete accounts whose grace period has expired.

    Administrator accounts are only deleted after their
    replacement has been approved, provisioned and confirmed.

    Returns the number of accounts permanently deleted.
    """

    now = timezone.now()

    due_request_ids = list(
        AccountDeletionRequest.objects.filter(
            status='PENDING',
            scheduled_deletion_at__lte=now
        ).values_list('pk', flat=True)
    )

    deleted_count = 0

    for request_id in due_request_ids:

        with transaction.atomic():

            # Read the user reference before acquiring locks.
            initial_request = (
                AccountDeletionRequest.objects
                .filter(pk=request_id, status='PENDING')
                .first()
            )

            if initial_request is None:
                continue

            user_id = initial_request.user_id

            if user_id is None:
                continue

            # Use the same lock order as login cancellation:
            # first User, then AccountDeletionRequest.
            user = (
                User.objects
                .select_for_update()
                .filter(pk=user_id)
                .first()
            )

            deletion_request = (
                AccountDeletionRequest.objects
                .select_for_update()
                .filter(
                    pk=request_id,
                    status='PENDING',
                    user_id=user_id,
                    scheduled_deletion_at__lte=now
                )
                .first()
            )

            if deletion_request is None or user is None:
                continue

            try:
                current_role = user.profile.role
            except Profile.DoesNotExist:
                continue

            if current_role != deletion_request.role_at_request:
                continue

            if deletion_request.role_at_request == 'ADMIN':

                if not administrator_replacement_is_ready(
                    deletion_request
                ):
                    continue

            deletion_request.status = 'COMPLETED'
            deletion_request.completed_at = now

            # Remove the nominated email from retained history.
            deletion_request.replacement_email = ''

            deletion_request.save(
                update_fields=[
                    'status',
                    'completed_at',
                    'replacement_email',
                ]
            )

            record_audit_event(
                action='ACCOUNT_PERMANENTLY_DELETED',
                actor=user,
                target_type='AccountDeletionRequest',
                target_id=deletion_request.pk,
                metadata={
                    'role': deletion_request.role_at_request,
                }
            )

            # User deletion cascades to Profile and other
            # personal data according to their FK policies.
            user.delete()

            deleted_count += 1

    return deleted_count


@transaction.atomic
def confirm_administrator_replacement_login(user):
    """
    Confirm that an approved replacement administrator
    has successfully logged in.
    """

    if not user.is_active:
        return False

    deletion_request = (
        AccountDeletionRequest.objects
        .select_for_update()
        .filter(
            status='PENDING',
            role_at_request='ADMIN',
            replacement_user=user,
            replacement_approved_at__isnull=False,
            replacement_confirmed_at__isnull=True
        )
        .first()
    )

    if deletion_request is None:
        return False

    if not hasattr(user, 'profile'):
        return False

    if user.profile.role != 'ADMIN':
        return False

    now = timezone.now()

    deletion_request.replacement_confirmed_at = now

    deletion_request.save(
        update_fields=['replacement_confirmed_at']
    )

    record_audit_event(
        action='ADMIN_REPLACEMENT_ACCESS_CONFIRMED',
        actor=user,
        target_type='AccountDeletionRequest',
        target_id=deletion_request.pk,
        metadata={}
    )

    return True
