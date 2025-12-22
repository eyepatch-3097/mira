import time
from django.core.management.base import BaseCommand
from django.db import transaction

from sources.models import DataSource, DataSourcePage
from sources.services.scrape import extract_text, summarize_text

class Command(BaseCommand):
    help = "Run background ingestion jobs for pending website sources."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Source worker started. Polling for pending jobs..."))

        while True:
            src = None
            with transaction.atomic():
                src = (
                    DataSource.objects.select_for_update(skip_locked=True)
                    .filter(source_type="website", status="pending")
                    .order_by("created_at")
                    .first()
                )
                if src:
                    src.status = "running"
                    src.save(update_fields=["status"])

            if not src:
                time.sleep(2)
                continue

            try:
                pages = DataSourcePage.objects.filter(source=src, selected=True).order_by("id")
                total = pages.count()
                src.selected_pages = total
                src.processed_pages = 0
                src.save(update_fields=["selected_pages", "processed_pages"])

                for p in pages:
                    try:
                        text = extract_text(p.url)
                        summary = summarize_text(text)

                        p.summary = summary
                        p.status = "done"
                        p.error = ""
                        p.save(update_fields=["summary", "status", "error", "updated_at"])
                    except Exception as e:
                        p.status = "failed"
                        p.error = str(e)[:300]
                        p.save(update_fields=["status", "error", "updated_at"])

                    # progress update
                    DataSource.objects.filter(pk=src.pk).update(processed_pages=src.processed_pages + 1)
                    src.processed_pages += 1

                # done
                src.status = "done"
                src.save(update_fields=["status"])
            except Exception as e:
                src.status = "failed"
                src.error_message = str(e)[:300]
                src.save(update_fields=["status", "error_message"])

            time.sleep(1)
