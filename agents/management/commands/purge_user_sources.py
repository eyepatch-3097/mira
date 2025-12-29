# agents/management/commands/purge_user_sources.py
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction

from sources.models import DataSource, DataSourcePage, Tag
from agents.models import AgentDataSource

try:
    from agents.models import AgentIndexItem  # if you have it
except Exception:
    AgentIndexItem = None


User = get_user_model()


class Command(BaseCommand):
    help = "Delete ALL DataSources (and derived pages/index) for a user. Useful for cleaning test data."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="User email to purge")
        parser.add_argument("--purge-tags", action="store_true", help="Also delete all Tags for this user")

    @transaction.atomic
    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        purge_tags = options["purge_tags"]

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise CommandError(f"No user found with email: {email}")

        # delete files on disk for uploaded sources
        sources = DataSource.objects.filter(user=user).select_related()
        for s in sources:
            if s.file:
                try:
                    s.file.delete(save=False)
                except Exception:
                    pass

        # remove agent->datasource links (in case FK doesn't cascade)
        AgentDataSource.objects.filter(agent__user=user).delete()

        # remove index rows if present
        if AgentIndexItem is not None:
            AgentIndexItem.objects.filter(agent__user=user).delete()

        # delete pages + sources
        DataSourcePage.objects.filter(source__user=user).delete()
        DataSource.objects.filter(user=user).delete()

        # optionally delete tags (ONLY for that user)
        if purge_tags:
            Tag.objects.filter(user=user).delete()

        self.stdout.write(self.style.SUCCESS(f"Purged sources for {email}."))
