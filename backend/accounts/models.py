from django.conf import settings
from django.db import models
from django.db.models import Q


class Profile(models.Model):

    ROLE_CHOICES = [
        ('LEARNER', 'Learner'),
        ('ADMIN', 'Administrator'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='LEARNER'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class GuestIdentity(models.Model):

    token_hash = models.CharField(
        max_length=64,
        unique=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"Guest identity #{self.pk}"


class GuestSession(models.Model):

    guest_identity = models.ForeignKey(
        GuestIdentity,
        on_delete=models.CASCADE,
        related_name='sessions'
    )

    token_hash = models.CharField(
        max_length=64,
        unique=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['guest_identity'],
                condition=Q(is_active=True),
                name='one_active_guest_session_per_identity'
            ),
        ]

    def __str__(self):
        return f"Guest session #{self.pk}"


class GuestUsage(models.Model):

    USAGE_TYPE_CHOICES = [
        ('QUIZ', 'Quiz'),
        ('SIMULATION', 'Simulation'),
    ]

    guest_identity = models.ForeignKey(
        GuestIdentity,
        on_delete=models.CASCADE,
        related_name='usage_records'
    )

    usage_type = models.CharField(
        max_length=12,
        choices=USAGE_TYPE_CHOICES
    )

    week_start = models.DateField()

    used_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    'guest_identity',
                    'usage_type',
                    'week_start',
                ],
                name='unique_guest_weekly_usage'
            ),
        ]

        ordering = ['-week_start']

    def __str__(self):
        return (
            f"Guest #{self.guest_identity_id} - "
            f"{self.usage_type} - {self.week_start}"
        )


class AccountDeletionRequest(models.Model):

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('CANCELLED', 'Cancelled'),
        ('COMPLETED', 'Completed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deletion_requests'
    )

    role_at_request = models.CharField(
        max_length=10,
        choices=Profile.ROLE_CHOICES
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    scheduled_deletion_at = models.DateTimeField()

    cancelled_at = models.DateTimeField(
        null=True,
        blank=True
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    # Administrator succession details
    replacement_email = models.EmailField(blank=True)

    replacement_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='incoming_admin_replacements'
    )

    replacement_approved_at = models.DateTimeField(
        null=True,
        blank=True
    )

    replacement_confirmed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user'],
                condition=Q(status='PENDING'),
                name='one_pending_deletion_per_user'
            ),
            models.UniqueConstraint(
                fields=['replacement_user'],
                condition=Q(
                    status='PENDING',
                    role_at_request='ADMIN',
                    replacement_user__isnull=False
                ),
                name='one_pending_admin_replacement'
            ),
        ]

        ordering = ['-requested_at']

    def __str__(self):
        return f"Deletion request #{self.pk} - {self.status}"


class SecurityAuditLog(models.Model):

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='security_audit_logs'
    )

    action = models.CharField(max_length=100)

    target_type = models.CharField(
        max_length=100,
        blank=True
    )

    target_id = models.CharField(
        max_length=100,
        blank=True
    )

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.action} - {self.created_at}"