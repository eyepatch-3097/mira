import re
from typing import List, Dict, Any

from agents.models import AgentIndexItem

WORD_RE = re.compile(r"[a-zA-Z0-9]+")

def _tokenize(q: str) -> List[str]:
    toks = [t.lower() for t in WORD_RE.findall(q or "")]
    stop = {"the","a","an","and","or","to","for","of","in","on","is","are","with","me","my","your","you","we","our"}
    toks = [t for t in toks if t not in stop and len(t) >= 3]
    return toks[:20]

def retrieve(*, agent, roles: List[str], query: str, limit: int = 10) -> List[Dict[str, Any]]:
    if not roles:
        return []

    q = (query or "").strip()
    toks = _tokenize(q)

    candidates = (
        AgentIndexItem.objects
        .filter(agent=agent, role__in=roles)
        .only("id","kind","role","title","url","text","tags_text","meta","source_id","page_id")
        [:300]
    )

    scored = []
    for item in candidates:
        text = (item.text or "").lower()
        tags = (item.tags_text or "").lower()
        title = (item.title or "").lower()
        url = (item.url or "").lower()

        score = 0.0
        for t in toks:
            if t in tags:
                score += 3.0
            if t in title:
                score += 2.0
            if t in url:
                score += 1.5
            if t in text:
                score += 1.0

        if score <= 0:
            continue
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    out = []
    for score, item in top:
        out.append({
            "id": item.id,
            "kind": item.kind,      # "page" or "source"
            "role": item.role,
            "title": item.title or "",
            "url": item.url or "",
            "text": (item.text or "")[:2000],
            "tags": [t for t in (item.tags_text or "").split(",") if t][:20],
            "meta": item.meta or {},
            "source_id": item.source_id,
            "page_id": item.page_id,
            "score": score,
        })
    return out
