# sources/management/commands/run_source_jobs.py
import time
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from sources.models import DataSource, DataSourcePage
from sources.services.scrape import extract_text_and_docs, summarize_with_openai, summarize_document_with_openai
from sources.services.documents import extract_text_from_pdf, extract_text_from_docx, extract_urls
import os



class Command(BaseCommand):
    help = "Run background ingestion jobs for pending website sources."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Source worker started. Polling for pending jobs..."))

        while True:
            src = None
            with transaction.atomic():
                src = (
                    DataSource.objects.select_for_update(skip_locked=True)
                    .filter(status="pending", source_type__in=["website", "document"])
                    .order_by("created_at")
                    .first()
                )
                if src:
                    src.status = "running"
                    src.error_message = ""
                    src.processed_pages = 0
                    src.save(update_fields=["status", "error_message", "processed_pages"])

            if not src:
                time.sleep(2)
                continue
            
            pages = DataSourcePage.objects.filter(source=src, selected=True).order_by("id")
            src.selected_pages = pages.count()
            src.save(update_fields=["selected_pages"])

            for p in pages:
                try:
                    p.status = "running"
                    p.save(update_fields=["status", "updated_at"])

                    if src.source_type == "document":
                        file_path = src.file.path
                        ext = os.path.splitext(src.original_filename or "")[1].lower()

                        if ext == ".pdf":
                            text = extract_text_from_pdf(file_path)
                        elif ext == ".docx":
                            text = extract_text_from_docx(file_path)
                        else:
                            raise RuntimeError("Unsupported document type")

                        urls = extract_urls(text)
                        summary = summarize_document_with_openai(
                            src.original_filename or "document", text, urls
                        )

                    else:
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

                # progress update (works for both website + document)
                DataSource.objects.filter(pk=src.pk).update(processed_pages=F("processed_pages") + 1)

            # finalize status AFTER all pages
            failed_count = DataSourcePage.objects.filter(source=src, selected=True, status="failed").count()
            empty_summary_count = DataSourcePage.objects.filter(source=src, selected=True, status="done", summary="").count()

            if failed_count > 0 or empty_summary_count > 0:
                src.status = "failed"
                src.error_message = f"Ingestion incomplete: failed_pages={failed_count}, empty_summaries={empty_summary_count}"
            else:
                src.status = "done"
                src.error_message = ""

            src.save(update_fields=["status", "error_message"])

            time.sleep(1)