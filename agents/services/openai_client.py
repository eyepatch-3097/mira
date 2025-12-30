import os
from django.conf import settings
from openai import OpenAI

_client = None

def get_openai_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client

    api_key = getattr(settings, "OPENAI_API_KEY", None) or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    _client = OpenAI(api_key=api_key)
    return _client
