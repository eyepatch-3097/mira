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
from sources.services.tagging import (
    extract_tags_with_openai,
    set_tags_for_source,
    set_tags_for_page,
)


class Command(BaseCommand):
    help = "Run background ingestion jobs for pending sources (website/document/sheet)."

    POLL_SLEEP_SECONDS = 2
    LOOP_SLEEP_SECONDS = 1

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Source worker started. Polling for pending jobs..."))

        while True:
            src = self._claim_next_source()
            if not src:
                time.sleep(self.POLL_SLEEP_SECONDS)
                continue

            try:
                self._process_source(src)
            except Exception as e:
                # Hard safety net so the worker never dies
                DataSource.objects.filter(pk=src.pk).update(
                    status="failed",
                    error_message=str(e)[:300],
                )

            time.sleep(self.LOOP_SLEEP_SECONDS)

    def _claim_next_source(self):
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

        if src.source_type == "website":
            self._process_website(src, pages)
        elif src.source_type == "document":
            self._process_document(src, pages)
        elif src.source_type == "sheet":
            self._process_sheet(src, pages)
        else:
            src.status = "failed"
            src.error_message = f"Unsupported source_type: {src.source_type}"
            src.save(update_fields=["status", "error_message"])

    # -----------------------------
    # WEBSITE
    # -----------------------------
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

                # Tagging is optional — don't fail ingestion if tagging fails
                try:
                    tags = extract_tags_with_openai(summary, max_tags=10)
                    set_tags_for_page(p, tags)
                except Exception:
                    pass

            except Exception as e:
                p.status = "failed"
                p.error = str(e)[:300]
                p.save(update_fields=["status", "error", "updated_at"])

            DataSource.objects.filter(pk=src.pk).update(processed_pages=F("processed_pages") + 1)

        self._finalize_source_from_pages(src)

    # -----------------------------
    # DOCUMENT
    # -----------------------------
    def _process_document(self, src: DataSource, pages):
        """
        Document source:
        - Parse file once
        - Generate ONE summary
        - Save summary to src.summary (for chatbot)
        - Also copy it to the first page row for UI consistency
        - Mark all selected pages done
        """
        try:
            pages.update(status="running", error="")

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

            # store for chatbot
            src.summary = summary
            src.save(update_fields=["summary"])

            # store for UI (use first selected page row)
            first = pages.first()
            if first:
                first.summary = summary
                first.status = "done"
                first.error = ""
                first.save(update_fields=["summary", "status", "error", "updated_at"])

            # mark all pages as done (even if you only show one)
            pages.update(status="done", error="")

            # tagging source-level
            try:
                tags = extract_tags_with_openai(summary, max_tags=10)
                set_tags_for_source(src, tags)
            except Exception:
                pass

            # progress fully complete
            src.processed_pages = src.selected_pages
            src.status = "done"
            src.error_message = ""
            src.save(update_fields=["processed_pages", "status", "error_message"])

        except Exception as e:
            pages.update(status="failed", error=str(e)[:300])
            src.processed_pages = src.selected_pages
            src.status = "failed"
            src.error_message = str(e)[:300]
            src.save(update_fields=["processed_pages", "status", "error_message"])

    # -----------------------------
    # SHEET
    # -----------------------------
    def _process_sheet(self, src: DataSource, pages):
        """
        Sheet sources:
        - Generate ONE source-level src.summary using stored previews
        - Mark all selected pages done so the UI is consistent
        - Tag source-level (NOT per-sheet)
        """
        try:
            pages.update(status="running", error="")

            lines = []
            for pg in pages:
                prev = pg.preview or {}
                headers = prev.get("headers") or []
                lines.append(f"Sheet/Table: {pg.url} | Columns: {', '.join(headers[:12])}")

            overview_text = "\n".join(lines)[:15000]
            context = (getattr(src, "source_context", "") or "").strip()

            summary = summarize_sheet_source_with_openai(src.name, context, overview_text)

            src.summary = summary
            src.processed_pages = src.selected_pages
            src.status = "done"
            src.error_message = ""
            src.save(update_fields=["summary", "processed_pages", "status", "error_message"])

            pages.update(status="done", error="")

            # Tagging source-level
            try:
                tags = extract_tags_with_openai(summary, max_tags=10)
                set_tags_for_source(src, tags)
            except Exception:
                pass

        except Exception as e:
            pages.update(status="failed", error=str(e)[:300])
            src.processed_pages = src.selected_pages
            src.status = "failed"
            src.error_message = str(e)[:300]
            src.save(update_fields=["processed_pages", "status", "error_message"])

    # -----------------------------
    # FINALIZE helper (website only)
    # -----------------------------
    def _finalize_source_from_pages(self, src: DataSource):
        failed = DataSourcePage.objects.filter(source=src, selected=True, status="failed").count()
        empty = DataSourcePage.objects.filter(source=src, selected=True, status="done", summary="").count()

        if failed > 0 or empty > 0:
            src.status = "failed"
            src.error_message = f"Ingestion incomplete: failed_pages={failed}, empty_summaries={empty}"
        else:
            src.status = "done"
            src.error_message = ""

        src.save(update_fields=["status", "error_message"])
