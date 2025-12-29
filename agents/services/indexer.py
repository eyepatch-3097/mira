# agents/services/indexer.py
from django.db import transaction

from agents.models import AgentIndexItem, AgentDataSource
from sources.models import DataSource, DataSourcePage

MAX_WEBSITE_PAGES_PER_SOURCE = 250   # keep it sane; you can tune later
MAX_SHEET_TABS_FOR_SCHEMA = 20

def _tags_to_text(obj) -> str:
    try:
        tags = list(obj.tags.values_list("name", flat=True))
        return ",".join(tags[:60])
    except Exception:
        return ""

def _page_title(url: str) -> str:
    # simple heuristic title from URL
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    tail = u.split("/")[-1] or u
    return tail.replace("-", " ").replace("_", " ")[:120]

@transaction.atomic
def rebuild_agent_index(agent):
    """
    Rebuilds index rows for a single agent.
    Safe to run after saving AgentDataSource links.
    """
    AgentIndexItem.objects.filter(agent=agent).delete()

    links = AgentDataSource.objects.filter(agent=agent).select_related("source")

    role_sources = {}
    for link in links:
        role_sources.setdefault(link.role, []).append(link.source_id)

    for role, source_ids in role_sources.items():
        sources = (
            DataSource.objects
            .filter(id__in=source_ids, user=agent.user)
            .prefetch_related("tags")
        )

        new_items = []

        for src in sources:
            # Only index completed sources/pages (otherwise retrieval becomes junk)
            if src.source_type != "custom" and src.status not in ["done", "failed"]:
                # skip pending/running/draft for non-custom
                continue

            if src.source_type == "website":
                pages = (
                    DataSourcePage.objects
                    .filter(
                        source=src,
                        selected=True,
                        status="done",
                    )
                    .exclude(summary="")
                    .prefetch_related("tags")
                    .order_by("-updated_at")[:MAX_WEBSITE_PAGES_PER_SOURCE]
                )

                src_tags = _tags_to_text(src)

                for p in pages:
                    page_tags = _tags_to_text(p)
                    combined_tags = ",".join([t for t in [page_tags, src_tags] if t])

                    new_items.append(
                        AgentIndexItem(
                            agent=agent,
                            role=role,
                            kind="page",
                            source=src,
                            page=p,
                            title=_page_title(p.url),
                            url=p.url,
                            text=(p.summary or "")[:12000],
                            tags_text=combined_tags[:12000],
                            meta={
                                "category": p.category,
                                "status": p.status,
                                "source_name": src.name,
                                "source_type": src.source_type,
                            },
                        )
                    )

            else:
                base_text = (src.summary or src.source_context or "").strip()

                if src.source_type == "custom":
                    # custom is always usable even without “done”
                    base_text = ((src.custom_text or "").strip() + "\n\n" + base_text).strip()

                if src.source_type == "sheet":
                    sheet_pages = (
                        DataSourcePage.objects
                        .filter(source=src, selected=True)
                        .order_by("id")[:MAX_SHEET_TABS_FOR_SCHEMA]
                    )
                    schema_lines = []
                    for pg in sheet_pages:
                        prev = pg.preview or {}
                        headers = prev.get("headers") or []
                        schema_lines.append(f"{pg.url}: {', '.join(headers[:15])}")
                    schema = "\n".join(schema_lines).strip()
                    if schema:
                        base_text = f"{schema}\n\n{base_text}".strip()

                new_items.append(
                    AgentIndexItem(
                        agent=agent,
                        role=role,
                        kind="source",
                        source=src,
                        page=None,
                        title=src.name,
                        url=src.domain_url or src.original_filename or "",
                        text=base_text[:12000],
                        tags_text=_tags_to_text(src)[:12000],
                        meta={
                            "source_type": src.source_type,
                            "source_name": src.name,
                            "status": src.status,
                        },
                    )
                )

        if new_items:
            AgentIndexItem.objects.bulk_create(new_items, ignore_conflicts=True)
