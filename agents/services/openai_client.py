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

    base_url = getattr(settings, "OPENAI_BASE_URL", None) or os.getenv("OPENAI_BASE_URL")

    kwargs = {"api_key": api_key, "max_retries": 2}
    if base_url:
        kwargs["base_url"] = base_url

    _client = OpenAI(**kwargs)
    return _client
