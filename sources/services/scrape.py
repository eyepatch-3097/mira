# sources/services/scrape.py
import os
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

DOC_EXTENSIONS = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx")


def extract_text_and_docs(url: str, timeout: int = 12):
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "MiraBot/0.1"})
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")

    doc_links = []
    for a in soup.select("a[href]"):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        abs_url = urljoin(url, href)
        if abs_url.lower().split("?")[0].endswith(DOC_EXTENSIONS):
            doc_links.append(abs_url)

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text, list(dict.fromkeys(doc_links))


def _extract_any_text(resp) -> str:
    """
    Robustly extract assistant text from Responses API,
    even if output contains tool/reasoning items.
    """
    # SDK convenience prop (best case)
    txt = (getattr(resp, "output_text", None) or "").strip()
    if txt:
        return txt

    # Fall back to scanning output items
    out = getattr(resp, "output", None) or []
    chunks = []
    for item in out:
        if getattr(item, "type", None) == "message":
            for c in getattr(item, "content", None) or []:
                if getattr(c, "type", None) == "output_text":
                    t = (getattr(c, "text", "") or "").strip()
                    if t:
                        chunks.append(t)
    return "\n".join(chunks).strip()


def summarize_with_openai(page_url: str, page_text: str, doc_links: list[str]) -> str:
    page_text = (page_text or "")[:20000]

    instructions = (
        "Write a clean, chatbot-friendly summary of the webpage.\n"
        "Output EXACTLY 2 short paragraphs separated by one blank line.\n"
        "Paragraph 1 (1–2 sentences): what this page is about and who it is for.\n"
        "Paragraph 2 (2–4 sentences): key details, include important numbers and primary keywords.\n"
        "Do NOT include any URLs in these paragraphs.\n"
        "No bullet points, no markdown, no headings."
    )

    input_text = (
        f"URL: {page_url}\n\n"
        f"PAGE TEXT (truncate):\n<<<{page_text}>>>"
    )

    response = client.responses.create(
        model=os.getenv("OPENAI_SUMMARY_MODEL", "gpt-5-nano"),
        instructions=instructions,
        input=input_text,
        # optional but helps ensure text output is present/clean
        text={"format": {"type": "text"}},
    )

    summary = _extract_any_text(response).strip()
    if not summary:
        rid = getattr(response, "id", None)
        status = getattr(response, "status", None)
        raise RuntimeError(f"OpenAI returned empty output (resp_id={rid}, status={status})")

    # Append links as a separate “section” (still plain text, no bullets)
    if doc_links:
        top = doc_links[:3]
        links_block = "\n".join(top)
        summary = f"{summary}\n\nImportant links:\n{links_block}"
    else:
        summary = f"{summary}\n\nImportant links:\nNone"

    return summary