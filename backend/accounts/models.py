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
