# accounts/views_analytics.py
from __future__ import annotations

from datetime import datetime, date, timedelta, time
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.core.exceptions import FieldError
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from django.core.exceptions import FieldDoesNotExist
from agents.models import Agent, Conversation, Message, AgentDataSource


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None


def _range_bounds(start_d: date | None, end_d: date | None):
    today = timezone.localdate()
    if not end_d:
        end_d = today
    if not start_d:
        start_d = end_d - timedelta(days=29)

    start_dt = timezone.make_aware(datetime.combine(start_d, time.min))
    end_dt = timezone.make_aware(datetime.combine(end_d + timedelta(days=1), time.min))
    return start_d, end_d, start_dt, end_dt


def _model_has_field(model, field_name: str) -> bool:
    try:
        model._meta.get_field(field_name)
        return True
    except FieldDoesNotExist:
        return False


def _count_sources_for_agents(agent_qs):
    """
    Counts distinct DataSource(s) linked to these agents via AgentDataSource.
    Only counts active sources if DataSource has is_active field.
    """
    qs = AgentDataSource.objects.filter(agent__in=agent_qs)

    # If DataSource has is_active, count only active sources
    try:
        ds_model = AgentDataSource._meta.get_field("source").remote_field.model
        if ds_model and _model_has_field(ds_model, "is_active"):
            qs = qs.filter(source__is_active=True)
    except Exception:
        pass

    return qs.values("source_id").distinct().count()


def _extract_intent_types_from_meta(meta: dict) -> list[str]:
    if not isinstance(meta, dict):
        return []
    dbg = meta.get("debug") or {}
    intents = dbg.get("intents") or []
    out: list[str] = []

    if isinstance(intents, list):
        for it in intents:
            if isinstance(it, str):
                out.append(it)
            elif isinstance(it, dict):
                t = (it.get("type") or "").strip()
                if t:
                    out.append(t)
    return out


def _is_unanswered(msg: Message) -> bool:
    txt = (msg.content or "").strip().lower()

    known_phrases = [
        "i'm sorry — i can only answer questions based on our configured",
        "i’m sorry — i can only answer questions based on our configured",
        "i can only answer questions based on our configured",
        "chat is not available right now",
    ]
    if any(p in txt for p in known_phrases):
        return True

    meta = msg.meta or {}
    dbg = (meta.get("debug") or {}) if isinstance(meta, dict) else {}
    evidence = dbg.get("evidence") or []
    intents = _extract_intent_types_from_meta(meta)

    if (not evidence) and ("UNKNOWN" in intents):
        return True

    return False


@login_required
@require_GET
def dashboard_insights_api(request):
    """
    GET /dashboard/insights/?agent_id=all&start=YYYY-MM-DD&end=YYYY-MM-DD
    Returns keys compatible with the dashboard UI: cards, sessions_over_time, intent_distribution, unanswered.
    """
    agent_id = (request.GET.get("agent_id") or "all").strip()
    start_d = _parse_date(request.GET.get("start"))
    end_d = _parse_date(request.GET.get("end"))

    start_d, end_d, start_dt, end_dt = _range_bounds(start_d, end_d)

    # Base agent queryset (user-scoped)
    agents_all = Agent.objects.filter(user=request.user).order_by("name")

    # Agent filter
    if agent_id != "all":
        try:
            agent_id_int = int(agent_id)
            agents_sel = agents_all.filter(id=agent_id_int)
        except Exception:
            agents_sel = agents_all.none()
    else:
        agents_sel = agents_all

    # Cards
    agents_live = agents_sel.filter(is_active=True).count()
    sources_live = _count_sources_for_agents(agents_sel.filter(is_active=True))

    # Conversations in range
    convos = Conversation.objects.filter(
        agent__in=agents_sel,
        created_at__gte=start_dt,
        created_at__lt=end_dt,
    )

    sessions_count = convos.count()

    # Leads: python-side (safe across DBs + JSONField)
    leads_count = 0
    for st in convos.values_list("state", flat=True):
        if isinstance(st, dict) and st.get("lead"):
            lead = st.get("lead") or {}
            if isinstance(lead, dict) and (lead.get("email") and lead.get("name")):
                leads_count += 1

    # Sessions over time
    daily = (
        convos.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
        .order_by("day")
    )
    sessions_series = [{"date": str(x["day"]), "count": x["count"]} for x in daily]

    # Intents + unanswered
    msgs = Message.objects.filter(
        conversation__in=convos,
        role="assistant",
        created_at__gte=start_dt,
        created_at__lt=end_dt,
    ).only("content", "meta")

    intent_counter = Counter()
    total_assistant = 0
    unanswered = 0

    for m in msgs.iterator(chunk_size=500):
        total_assistant += 1
        if _is_unanswered(m):
            unanswered += 1
        for t in _extract_intent_types_from_meta(m.meta or {}):
            intent_counter[t] += 1

    unanswered_pct = (unanswered / total_assistant * 100.0) if total_assistant else 0.0

    if unanswered_pct <= 10:
        mood = "smile"
    elif unanswered_pct <= 25:
        mood = "meh"
    else:
        mood = "sad"

    intent_distribution = [{"intent": k, "count": v} for k, v in intent_counter.most_common()]

    return JsonResponse({
        "ok": True,
        "filters": {
            "agent_id": agent_id,
            "start": str(start_d),
            "end": str(end_d),
        },
        "cards": {
            "agents_live": agents_live,
            "data_sources_live": sources_live,
            "chat_sessions": sessions_count,
            "leads_submitted": leads_count,
        },
        "sessions_over_time": sessions_series,
        "intent_distribution": intent_distribution,
        "unanswered": {
            "percent": round(unanswered_pct, 1),
            "mood": mood,
            "total_assistant_msgs": total_assistant,
            "unanswered_msgs": unanswered,
        },
        "agents": [{"id": a.id, "name": a.name} for a in agents_all],
    })
