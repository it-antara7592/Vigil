
from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import (
    AccountDeletionRequest,
    Profile,
)
from accounts.services import record_audit_event


User = get_user_model()


class Command(BaseCommand):

    help = (
        "Provision a replacement administrator for a pending "
        "administrator deletion request."
    )

    def handle(self, *args, **options):

        request_id = input(
            "Enter the administrator deletion request ID: "
        ).strip()

        if not request_id.isdigit():
            raise CommandError("A valid request ID is required.")

        with transaction.atomic():

            try:
                deletion_request = (
                    AccountDeletionRequest.objects
                    .select_for_update()
                    .get(
                        pk=int(request_id),
                        status='PENDING',
                        role_at_request='ADMIN'
                    )
                )
            except AccountDeletionRequest.DoesNotExist:
                raise CommandError(
                    "No matching pending administrator deletion "
                    "request was found."
                )

            if deletion_request.scheduled_deletion_at <= timezone.now():
                raise CommandError(
                    "The administrator deletion grace period has "
                    "already expired. Review the request before "
                    "provisioning a replacement."
                )

            if deletion_request.replacement_user_id:
                raise CommandError(
                    "A replacement administrator is already linked "
                    "to this request."
                )

            nominated_email = (
                deletion_request.replacement_email.strip().lower()
            )

            if not nominated_email:
                raise CommandError(
                    "This deletion request has no nominated replacement."
                )

            self.stdout.write(
                f"Nominated replacement: {nominated_email}"
            )

            self.stdout.write(
                "\nEnter the identities of the two project owners "
                "who approved this appointment."
            )

            approver_one = input("First approver: ").strip()
            approver_two = input("Second approver: ").strip()

            if not approver_one or not approver_two:
                raise CommandError(
                    "Both project-owner approvals must be documented."
                )

            if approver_one.casefold() == approver_two.casefold():
                raise CommandError(
                    "Two different project owners must approve."
                )

            approval_confirmation = input(
                "Have both approvals been independently verified? "
                "Type YES to continue: "
            ).strip()

            if approval_confirmation != "YES":
                raise CommandError(
                    "Administrator provisioning cancelled."
                )

            existing_user = User.objects.filter(
                email__iexact=nominated_email
            ).first()

            if existing_user:

                user = User.objects.select_for_update().get(
                    pk=existing_user.pk
                )

                if not user.is_active:
                    raise CommandError(
                        "The nominated account is inactive."
                    )

                if user.is_superuser:
                    raise CommandError(
                        "A Django superuser account cannot be used "
                        "as a Vigil replacement administrator."
                    )

                if not hasattr(user, 'profile'):
                    raise CommandError(
                        "The nominated account does not have a profile."
                    )

                if user.profile.role != 'LEARNER':
                    raise CommandError(
                        "The nominated account must be a learner account."
                    )

                self.stdout.write(
                    "An existing learner account will be promoted."
                )

            else:

                self.stdout.write(
                    "No existing account was found. "
                    "A new administrator account will be created."
                )

                username = input("Username: ").strip()
                first_name = input("First name: ").strip()
                last_name = input("Last name (optional): ").strip()

                if not username or not first_name:
                    raise CommandError(
                        "Username and first name are required."
                    )

                if User.objects.filter(
                    username__iexact=username
                ).exists():
                    raise CommandError(
                        "That username is already in use."
                    )

                password = getpass("Set initial password: ")
                confirm_password = getpass("Confirm initial password: ")

                if not password or password != confirm_password:
                    raise CommandError(
                        "The passwords are empty or do not match."
                    )

                user = User(
                    username=username,
                    email=nominated_email,
                    first_name=first_name,
                    last_name=last_name
                )

                # Apply Django's configured password validators.
                try:
                    validate_password(password, user)
                except ValidationError as error:
                    messages = "\n- ".join(error.messages)

                    raise CommandError(
                        "The password does not meet the requirements:\n"
                        f"- {messages}"
                    )

                user.set_password(password)

                user.full_clean(
                    exclude=['password', 'last_login', 'date_joined']
                )
                user.save()

                Profile.objects.create(
                    user=user,
                    role='LEARNER'
                )

            # Grant Vigil's application-level administrator role.
            # Do not automatically grant Django superuser privileges.
            user.profile.role = 'ADMIN'
            user.profile.save(update_fields=['role'])

            user.is_staff = True
            user.save(update_fields=['is_staff'])

            now = timezone.now()

            deletion_request.replacement_user = user
            deletion_request.replacement_email = ''
            deletion_request.replacement_approved_at = now

            deletion_request.save(
                update_fields=[
                    'replacement_user',
                    'replacement_email',
                    'replacement_approved_at',
                ]
            )

            record_audit_event(
                action='ADMIN_REPLACEMENT_PROVISIONED',
                actor=None,
                target_type='AccountDeletionRequest',
                target_id=deletion_request.pk,
                metadata={
                    'replacement_user_id': user.pk,
                    'approvers': [
                        approver_one,
                        approver_two,
                    ],
                    'approval_method': 'Externally verified by maintainer',
                }
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Administrator account provisioned for {nominated_email}."
            )
        )

        self.stdout.write(
            "The replacement must now log in successfully to confirm access."
        )
