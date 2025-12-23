# sources/management/commands/run_source_jobs.py
import os
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F

from sources.models import DataSource, DataSourcePage
from sources.services.scrape import (
    extract_text_and_docs,
    summarize_with_openai,
    summarize_document_with_openai,
    summarize_sheet_source_with_openai,
)
from sources.services.documents import (
    extract_text_from_pdf,
    extract_text_from_docx,
    extract_urls,
)


class Command(BaseCommand):
    help = "Run background ingestion jobs for pending sources (website/document/sheet)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Source worker started. Polling for pending jobs..."))

        while True:
            src = self._claim_next_source()
            if not src:
                time.sleep(2)
                continue

            try:
                self._process_source(src)
            except Exception as e:
                # last-resort safety net so worker never dies
                DataSource.objects.filter(pk=src.pk).update(
                    status="failed",
                    error_message=str(e)[:300],
                )

            time.sleep(1)

    def _claim_next_source(self):
        """
        Atomically claim ONE pending DataSource for processing.
        """
        with transaction.atomic():
            src = (
                DataSource.objects.select_for_update(skip_locked=True)
                .filter(status="pending", source_type__in=["website", "document", "sheet"])
                .order_by("created_at")
                .first()
            )
            if not src:
                return None

            src.status = "running"
            src.error_message = ""
            src.processed_pages = 0
            src.save(update_fields=["status", "error_message", "processed_pages"])
            return src

    def _process_source(self, src: DataSource):
        pages = DataSourcePage.objects.filter(source=src, selected=True).order_by("id")
        total = pages.count()

        src.selected_pages = total
        src.processed_pages = 0
        src.save(update_fields=["selected_pages", "processed_pages"])

        if total == 0:
            src.status = "failed"
            src.error_message = "No selected pages/items to process."
            src.save(update_fields=["status", "error_message"])
            return

        if src.source_type == "sheet":
            self._process_sheet(src, pages)
            return

        if src.source_type == "document":
            self._process_document(src, pages)
            return

        # default: website
        self._process_website(src, pages)

    def _process_website(self, src: DataSource, pages):
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

        failed = DataSourcePage.objects.filter(source=src, selected=True, status="failed").count()
        empty = DataSourcePage.objects.filter(source=src, selected=True, status="done", summary="").count()

        if failed > 0 or empty > 0:
            src.status = "failed"
            src.error_message = f"Ingestion incomplete: failed_pages={failed}, empty_summaries={empty}"
        else:
            src.status = "done"
            src.error_message = ""

        src.save(update_fields=["status", "error_message"])

    def _process_document(self, src: DataSource, pages):
        """
        Document sources: typically 1 DataSourcePage row that represents the file.
        We store the summary in that page.summary (and show it like other pages).
        """
        p = pages.first()

        try:
            p.status = "running"
            p.save(update_fields=["status", "updated_at"])

            file_path = src.file.path
            ext = os.path.splitext(src.original_filename or "")[1].lower()

            if ext == ".pdf":
                text = extract_text_from_pdf(file_path)
            elif ext == ".docx":
                text = extract_text_from_docx(file_path)
            else:
                raise RuntimeError("Unsupported document type (only PDF/DOCX).")

            urls = extract_urls(text)
            summary = summarize_document_with_openai(src.original_filename or "document", text, urls)

            p.summary = summary
            p.status = "done"
            p.error = ""
            p.save(update_fields=["summary", "status", "error", "updated_at"])

        except Exception as e:
            p.status = "failed"
            p.error = str(e)[:300]
            p.save(update_fields=["status", "error", "updated_at"])

        # processed 1/1
        DataSource.objects.filter(pk=src.pk).update(processed_pages=F("processed_pages") + 1)

        failed = DataSourcePage.objects.filter(source=src, selected=True, status="failed").count()
        empty = DataSourcePage.objects.filter(source=src, selected=True, status="done", summary="").count()

        if failed > 0 or empty > 0:
            src.status = "failed"
            src.error_message = f"Ingestion incomplete: failed_pages={failed}, empty_summaries={empty}"
        else:
            src.status = "done"
            src.error_message = ""

        src.save(update_fields=["status", "error_message"])

    def _process_sheet(self, src: DataSource, pages):
        """
        Sheet sources:
        - We DO NOT require per-sheet page.summary
        - We generate ONE source-level src.summary from previews
        - We mark all pages done (or failed) so history UI looks consistent
        """
        try:
            # mark all running
            pages.update(status="running", error="")

            lines = []
            for pg in pages:
                prev = pg.preview or {}
                headers = prev.get("headers") or []
                # pg.url is your sheet name / table label
                lines.append(f"Sheet/Table: {pg.url} | Columns: {', '.join(headers[:12])}")

            overview_text = "\n".join(lines)[:15000]
            context = getattr(src, "source_context", "") or ""

            summary = summarize_sheet_source_with_openai(src.name, context, overview_text)
            src.summary = summary

            pages.update(status="done", error="")

            src.processed_pages = src.selected_pages
            src.status = "done"
            src.error_message = ""
            src.save(update_fields=["summary", "processed_pages", "status", "error_message"])

        except Exception as e:
            pages.update(status="failed", error=str(e)[:300])
            src.status = "failed"
            src.error_message = str(e)[:300]
            src.processed_pages = src.selected_pages
            src.save(update_fields=["status", "error_message", "processed_pages"])
