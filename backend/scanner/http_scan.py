import httpx
from urllib.parse import urlparse
from bs4 import BeautifulSoup

SECURITY_HEADERS = [
    "content-security-policy","strict-transport-security","x-content-type-options",
    "x-frame-options","referrer-policy","permissions-policy","cross-origin-opener-policy","cross-origin-resource-policy",
]

async def fetch_http(url: str, timeout_sec: float = 15.0, max_bytes: int = 2_000_000, user_agent: str | None = None):
    headers = {"User-Agent": user_agent or "URLScanner/agent-v1"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout_sec, headers=headers) as client:
        resp = await client.get(url)
        body = resp.content[:max_bytes]
        soup = None; title=None; gen=None; scripts=[]; links=[]; text_sample=None
        if "text/html" in resp.headers.get("content-type",""):
            soup = BeautifulSoup(body, "html.parser")
            title = (soup.title.string.strip() if soup.title and soup.title.string else None)
            m = soup.find("meta", attrs={"name":"generator"})
            if m and m.get("content"): gen = m.get("content").strip()
            scripts = [s.get("src") for s in soup.find_all("script") if s.get("src")]
            links = [a.get("href") for a in soup.find_all("a") if a.get("href")]
            text_sample = soup.get_text(separator=" ", strip=True)[:500]
        sec = {h: {"present": resp.headers.get(h) is not None, "value": resp.headers.get(h)} for h in SECURITY_HEADERS}
        result = {
            "final_url": str(resp.url),
            "status_code": resp.status_code,
            "http_version": resp.http_version,
            "headers": dict(resp.headers),
            "content_type": resp.headers.get("content-type"),
            "content_length": int(resp.headers.get("content-length")) if resp.headers.get("content-length") else len(body),
            "truncated": len(resp.content) > len(body),
            "title": title,
            "meta_generator": gen,
            "script_src": scripts[:200],
            "link_hrefs": links[:500],
            "text_sample": text_sample,
            "security_headers": sec,
            "redirect_history": [str(r.headers.get("location")) for r in resp.history if r.headers.get("location")],
        }
        try:
            parsed = urlparse(str(resp.url))
            rob = await client.get(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
            result["robots_txt_present"] = (rob.status_code == 200)
            if rob.status_code == 200:
                result["robots_txt_sample"] = rob.text[:1000]
        except Exception as e:
            result["robots_error"] = str(e)
        return result