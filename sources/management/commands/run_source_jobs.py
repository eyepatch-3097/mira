# sources/management/commands/run_source_jobs.py
import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from sources.models import DataSource, DataSourcePage
from sources.services.scrape import extract_text_and_docs, summarize_with_openai


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
                    src.error_message = ""
                    src.save(update_fields=["status", "error_message"])

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
                        p.status = "running"
                        p.save(update_fields=["status", "updated_at"])

                        text, doc_links = extract_text_and_docs(p.url)
                        summary = summarize_with_openai(p.url, text, doc_links)

                        p.summary = summary
                        p.status = "done"
                        p.error = ""
                        p.save(update_fields=["summary", "status", "error", "updated_at"])

                    except Exception as e:
                        p.status = "failed"
                        p.error = str(e)[:300]
                        p.save(update_fields=["status", "error", "updated_at"])

                    DataSource.objects.filter(pk=src.pk).update(processed_pages=F("processed_pages") + 1)

                failed_count = DataSourcePage.objects.filter(source=src, status="failed").count()
                empty_summary_count = DataSourcePage.objects.filter(source=src, status="done").filter(summary="").count()

                if failed_count > 0 or empty_summary_count > 0:
                    src.status = "failed"
                    src.error_message = f"Ingestion incomplete: failed_pages={failed_count}, empty_summaries={empty_summary_count}"
                else:
                    src.status = "done"

                src.save(update_fields=["status", "error_message"])

            except Exception as e:
                src.status = "failed"
                src.error_message = str(e)[:300]
                src.save(update_fields=["status", "error_message"])

            time.sleep(1)
