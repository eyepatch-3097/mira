import socket
import ipaddress
from urllib.parse import urlparse

def is_public_host(hostname: str) -> bool:
    try:
        ip = socket.gethostbyname(hostname)
        addr = ipaddress.ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast)
    except Exception:
        return False

def normalize_domain_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    u = urlparse(raw)
    if u.scheme not in ("http", "https"):
        raise ValueError("Only http/https URLs are supported.")
    if not u.netloc:
        raise ValueError("Invalid domain URL.")
    if not is_public_host(u.hostname or ""):
        raise ValueError("That domain is not allowed (private/internal host).")
    # Normalize: keep scheme+netloc only
    return f"{u.scheme}://{u.netloc}"
