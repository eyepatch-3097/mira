import re
import requests
from bs4 import BeautifulSoup

def extract_text(url: str, timeout: int = 12) -> str:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "MiraBot/0.1"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    # remove junk
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def summarize_text(text: str) -> str:
    # Placeholder until OpenAI integration:
    # take first ~3 sentences or ~500 chars
    if not text:
        return ""
    snippet = text[:1200]
    parts = re.split(r"(?<=[.!?])\s+", snippet)
    summary = " ".join(parts[:3]).strip()
    return summary[:600]
