# agents/services/retrieval.py
import re
from django.db.models import Q
from agents.models import AgentIndexItem

WORD_RE = re.compile(r"[a-zA-Z0-9]+")

STOP = {
    "the","a","an","and","or","to","for","of","in","on","is","are","with",
    "me","my","your","you","we","i","it","this","that","what","who","where","when",
    "how","can","could","would","should","do","does","did","about"
}


def _tokenize(q: str):
    toks = [t.lower() for t in WORD_RE.findall(q or "")]
    toks = [t for t in toks if t not in STOP]
    # keep short but meaningful
    return toks[:20]


def _as_out(item, score: float):
    return {
        "id": item.id,
        "kind": item.kind,
        "role": item.role,
        "title": item.title or "",
        "url": item.url or "",
        "text": (item.text or "")[:2000],
        "tags": [t.strip() for t in (item.tags_text or "").split(",") if t.strip()][:15],
        "meta": item.meta or {},
        "source_id": item.source_id,
        "page_id": item.page_id,
        "score": float(score),
    }


def retrieve(agent, roles, query: str, limit: int = 8, candidate_cap: int = 250):
    """
    Lexical retrieval (v1):
    - Uses DB filtering to narrow candidates
    - Scores title/tags/text/url
    - Never returns empty unless there is literally no index for those roles
    """
    roles = list(roles or [])
    q = (query or "").strip()
    if not roles:
        return []

    tokens = _tokenize(q)

    base_qs = (
        AgentIndexItem.objects
        .filter(agent=agent, role__in=roles)
        .only("id", "kind", "role", "title", "url", "text", "tags_text", "meta", "source_id", "page_id")
        .order_by("-id")  # stable + usually newest last indexed is most relevant
    )

    # If we have tokens, filter candidates in DB using OR across fields.
    # If we don't, just take a reasonable recent slice.
    if tokens:
        q_obj = Q()
        for t in tokens:
            q_obj |= Q(tags_text__icontains=t)
            q_obj |= Q(title__icontains=t)
            q_obj |= Q(text__icontains=t)
            q_obj |= Q(url__icontains=t)
        candidates = list(base_qs.filter(q_obj)[:candidate_cap])
    else:
        candidates = list(base_qs[:candidate_cap])

    if not candidates:
        return []

    scored = []
    for item in candidates:
        title = (item.title or "").lower()
        text = (item.text or "").lower()
        tags = (item.tags_text or "").lower()
        url = (item.url or "").lower()

        score = 0.0
        for t in tokens:
            # strong signals
            if t and t in tags:
                score += 3.0
            if t and t in title:
                score += 2.5
            if t and t in url:
                score += 1.5
            if t and t in text:
                score += 1.0

        # If tokens exist and score is 0, skip.
        if tokens and score <= 0:
            continue

        # If no tokens, give baseline score so we return something.
        if not tokens:
            score = 0.1

        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Fallback: if nothing matched but index exists, return top items (baseline relevance)
    if not scored:
        fallback = list(base_qs[:limit])
        return [_as_out(it, 0.05) for it in fallback]

    top = scored[:limit]
    return [_as_out(item, score) for score, item in top]