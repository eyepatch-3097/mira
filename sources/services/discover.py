import re
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SITEMAP_PATHS = ["/sitemap.xml", "/sitemap_index.xml"]

def _same_domain(base: str, url: str) -> bool:
    return urlparse(base).netloc == urlparse(url).netloc

def _clean_url(url: str) -> str:
    url = url.split("#")[0]
    return url.rstrip("/")

def discover_urls(domain_url: str, max_urls: int = 300, timeout: int = 10) -> list[str]:
    urls = []
    seen = set()

    # 1) Try sitemap(s)
    for path in SITEMAP_PATHS:
        sm_url = urljoin(domain_url + "/", path.lstrip("/"))
        try:
            r = requests.get(sm_url, timeout=timeout, headers={"User-Agent": "MiraBot/0.1"})
            if r.status_code >= 400 or "xml" not in (r.headers.get("Content-Type", "").lower()):
                continue
            soup = BeautifulSoup(r.text, "xml")
            locs = [loc.get_text(strip=True) for loc in soup.find_all("loc")]
            for u in locs:
                u = _clean_url(u)
                if u and _same_domain(domain_url, u) and u not in seen:
                    seen.add(u)
                    urls.append(u)
                    if len(urls) >= max_urls:
                        return urls
            if urls:
                return urls
        except Exception:
            continue

    # 2) Fallback: crawl from homepage
    q = deque([domain_url])
    seen.add(domain_url)

    while q and len(urls) < max_urls:
        current = q.popleft()
        try:
            r = requests.get(current, timeout=timeout, headers={"User-Agent": "MiraBot/0.1"})
            if r.status_code >= 400:
                continue
            urls.append(_clean_url(current))
            soup = BeautifulSoup(r.text, "lxml")

            for a in soup.select("a[href]"):
                href = a.get("href", "").strip()
                if not href:
                    continue
                if href.startswith(("mailto:", "tel:", "javascript:")):
                    continue
                nxt = _clean_url(urljoin(current, href))
                if not nxt.startswith(("http://", "https://")):
                    continue
                if not _same_domain(domain_url, nxt):
                    continue
                # skip obvious asset links
                if re.search(r"\.(png|jpg|jpeg|gif|webp|svg|pdf|zip)$", nxt, re.I):
                    continue
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        except Exception:
            continue

    return urls
