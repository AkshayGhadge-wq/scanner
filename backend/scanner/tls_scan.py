import asyncio, ssl, socket
from urllib.parse import urlparse
from datetime import datetime

async def fetch_tls_info(url: str):
    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port or 443

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _blocking_tls_probe, hostname, port)

def _format_ts(ts):
    try:
        return datetime.strptime(ts, "%b %d %H:%M:%S %Y %Z").isoformat()
    except Exception:
        return ts

def _blocking_tls_probe(hostname: str, port: int):
    ctx = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
            cert = ssock.getpeercert()
            tls_version = ssock.version()
            cipher = ssock.cipher()
    return {
        "hostname": hostname,
        "port": port,
        "tls_version": tls_version,
        "cipher": {"name": cipher[0], "protocol": cipher[1], "bits": cipher[2]},
        "subject": dict(x[0] for x in cert.get("subject", [])) if cert else None,
        "issuer": dict(x[0] for x in cert.get("issuer", [])) if cert else None,
        "notBefore": _format_ts(cert.get("notBefore")) if cert and cert.get("notBefore") else None,
        "notAfter": _format_ts(cert.get("notAfter")) if cert and cert.get("notAfter") else None,
        "subjectAltName": [v for k, v in cert.get("subjectAltName", [])] if cert and cert.get("subjectAltName") else None,
    }