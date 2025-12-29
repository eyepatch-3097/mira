# agents/services/gating.py
from django.utils import timezone
from agents.models import LeadCapture, DocumentAccessToken
from sources.models import DataSource


def needs_lead(conversation, gating_type: str) -> bool:
    state = conversation.state or {}
    # if already captured in this conversation, don’t ask again
    return not state.get(f"{gating_type}_lead_captured", False)


def mark_lead_captured(conversation, gating_type: str, lead_id: int):
    state = conversation.state or {}
    state[f"{gating_type}_lead_captured"] = True
    state[f"{gating_type}_lead_id"] = lead_id
    conversation.state = state
    conversation.save(update_fields=["state", "updated_at"])


def create_lead(agent, conversation, name: str, email: str, source: str, question: str = ""):
    lead = LeadCapture.objects.create(
        agent=agent,
        conversation=conversation,
        name=name.strip(),
        email=email.strip(),
        source=source,
        question=question[:2000],
    )
    return lead


def mint_doc_token(lead, data_source: DataSource, hours_valid: int = 72):
    return DocumentAccessToken.mint(lead=lead, data_source=data_source, hours_valid=hours_valid)
