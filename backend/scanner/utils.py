from urllib.parse import urlparse
def normalize_url(url: str) -> str:
    if "://" not in url: url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http","https"): raise ValueError("Only http/https supported")
    return url