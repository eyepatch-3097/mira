# sources/services/documents.py
import re
from pypdf import PdfReader
from docx import Document as DocxDocument

URL_RE = re.compile(r"https?://[^\s\)\]\}<>\"']+")

def _clean_text(t: str) -> str:
    t = re.sub(r"\s+", " ", (t or "")).strip()
    return t

def extract_urls(text: str, limit: int = 10) -> list[str]:
    urls = URL_RE.findall(text or "")
    # de-dupe preserve order
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
        if len(out) >= limit:
            break
    return out

def extract_text_from_pdf(path: str, max_chars: int = 60000) -> str:
    reader = PdfReader(path)
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
        if sum(len(p) for p in parts) >= max_chars:
            break
    return _clean_text(" ".join(parts))[:max_chars]

def extract_text_from_docx(path: str, max_chars: int = 60000) -> str:
    doc = DocxDocument(path)
    parts = [p.text for p in doc.paragraphs if (p.text or "").strip()]
    return _clean_text(" ".join(parts))[:max_chars]
