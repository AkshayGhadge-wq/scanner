from typing import Dict, Any, List
def _match_frameworks(http: Dict[str, Any]) -> List[str]:
    fw=set(); headers={k.lower():v for k,v in (http.get("headers") or {}).items()}
    gen=(http.get("meta_generator") or "").lower(); server=(headers.get("server") or "").lower()
    powered=(headers.get("x-powered-by") or "").lower()
    scripts=[s.lower() for s in (http.get("script_src") or [])]
    if "wordpress" in gen or any("/wp-" in s for s in scripts): fw.add("WordPress")
    if any("_next/" in s for s in scripts): fw.add("Next.js")
    if any("react" in s for s in scripts): fw.add("React")
    if "nginx" in server: fw.add("nginx")
    if "apache" in server: fw.add("apache")
    if "express" in powered: fw.add("Express")
    return sorted(fw)
def _site_kind(http: Dict[str, Any]) -> str:
    ct=(http.get("content_type") or "").lower()
    if "text/html" in ct: return "dynamic_or_static_html"
    if "json" in ct or "xml" in ct: return "api"
    return "unknown"
def fingerprint_tech(url: str, http: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "frameworks": _match_frameworks(http),
        "site_kind": _site_kind(http),
        "server": (http.get("headers", {}).get("server")),
        "x_powered_by": (http.get("headers", {}).get("x-powered-by")),
        "uses_https": url.lower().startswith("https://"),
    }