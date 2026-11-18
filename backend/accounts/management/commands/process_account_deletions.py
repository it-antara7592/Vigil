from django.core.management.base import BaseCommand

from accounts.services import process_due_deletion_requests


class Command(BaseCommand):

    help = "Permanently delete accounts whose grace period has expired."

    def handle(self, *args, **options):

        deleted_count = process_due_deletion_requests()

        self.stdout.write(
            self.style.SUCCESS(
                f"Completed permanent deletion for {deleted_count} account(s)."
            )
        )