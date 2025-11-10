import asyncio
import time
import uuid
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional, Dict, Any, List
from scanner.http_scan import fetch_http
from scanner.tls_scan import fetch_tls_info
from scanner.fingerprint import fingerprint_tech
from scanner.utils import normalize_url
from scanner.planner import plan_resources

# ---------------- In-memory "DB" for demo ----------------
SOURCES: Dict[str, Dict[str, Any]] = {}
AGENTS: Dict[str, Dict[str, Any]] = {}
JOBS: Dict[str, Dict[str, Any]] = {}
AGENT_INBOX: Dict[str, List[str]] = {}   # agent_id -> [job_ids]

def _now(): return int(time.time())

def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

def make_enroll_token(source_id: str) -> str:
    # demo token (NOT secure). For prod: JWT with expiry & signature.
    return f"tok:{source_id}:{_now()+1800}"  # 30 min TTL

def verify_enroll_token(token: str, source_id: str) -> bool:
    try:
        _, sid, exp = token.split(":")
        return sid == source_id and int(exp) >= _now()
    except Exception:
        return False

app = FastAPI(title="Scanner + Agent Control Plane", version="0.1.0",
              description="URL scanner + VM agent enrollment and job orchestration (MVP)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------- URL scanner models ----------------
class ScanRequest(BaseModel):
    url: HttpUrl
    max_bytes: int = 2_000_000
    timeout_sec: float = 15.0
    user_agent: Optional[str] = None

@app.get("/health")
def health():
    return {"ok": True, "time": _now()}

@app.post("/scan")
async def scan(req: ScanRequest):
    url = normalize_url(str(req.url))
    http_result = await fetch_http(url, timeout_sec=req.timeout_sec, max_bytes=req.max_bytes, user_agent=req.user_agent)
    tls_result: Optional[Dict[str, Any]] = None
    if url.lower().startswith("https://"):
        try:
            tls_result = await fetch_tls_info(url)
        except Exception as e:
            tls_result = {"error": f"TLS probe failed: {e}"}

    fp = fingerprint_tech(url, http_result)
    recs = []
    if http_result.get("security_headers"):
        missing = [k for k, v in http_result["security_headers"].items() if not v["present"]]
        if missing:
            recs.append({"type": "hardening","title": "Add recommended security headers","missing": missing})
    if http_result.get("http_version") == "HTTP/1.1":
        recs.append({"type": "performance","title": "Enable HTTP/2 or HTTP/3 via CDN/proxy"})

    plan = plan_resources({"http": http_result, "fingerprint": fp})
    return {
        "input": {"url": url},
        "http": http_result,
        "tls": tls_result,
        "fingerprint": fp,
        "recommendations": recs,
        "plan": plan
    }

# ---------------- Agent: public UI endpoints ----------------
class CreateSourceReq(BaseModel):
    name: str
    os: str = "linux"  # linux | windows
    labels: Optional[Dict[str, str]] = None

@app.post("/sources")
def create_source(req: CreateSourceReq):
    sid = new_id("src")
    SOURCES[sid] = {
        "source_id": sid, "name": req.name, "os": req.os, "labels": req.labels or {},
        "status": "pending_enroll", "created_at": _now(), "agent_id": None, "last_seen": None
    }
    token = make_enroll_token(sid)
    api_base = "http://localhost:8080"  # change if deployed
    install_linux = f"curl -fsSL {api_base}/agent/install.sh | sudo bash -s -- --api={api_base} --source-id={sid} --enroll-token={token}"
    install_win = f"powershell -ExecutionPolicy Bypass -Command \"iwr {api_base}/agent/install.ps1 -UseBasicParsing | iex; Install-Agent -Api '{api_base}' -SourceId '{sid}' -EnrollToken '{token}'\""
    return {
        "source": SOURCES[sid],
        "enroll_token": token,
        "install": {"linux": install_linux, "windows": install_win}
    }

@app.get("/sources/{source_id}")
def get_source(source_id: str):
    src = SOURCES.get(source_id)
    if not src: raise HTTPException(404, "source not found")
    return src

# Trigger a host scan
class ScanHostReq(BaseModel):
    source_id: str
    kind: str = "host_inventory"

@app.post("/scanHost")
def scan_host(req: ScanHostReq):
    src = SOURCES.get(req.source_id)
    if not src or not src.get("agent_id"):
        raise HTTPException(400, "source not enrolled/online")
    job_id = new_id("job")
    JOBS[job_id] = {
        "job_id": job_id, "source_id": req.source_id, "agent_id": src["agent_id"],
        "kind": req.kind, "status": "queued", "created_at": _now(),
        "progress": {"phase": "queued", "pct": 0}, "chunks": []
    }
    AGENT_INBOX.setdefault(src["agent_id"], []).append(job_id)
    return {"job_id": job_id}

@app.get("/scanJobs/{job_id}/status")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job: raise HTTPException(404, "job not found")
    return {"job_id": job_id, "status": job["status"], "progress": job["progress"]}

@app.get("/sources")
def list_sources():
    return list(SOURCES.values())

# ---------------- Agent: agent-only endpoints ----------------
class EnrollReq(BaseModel):
    source_id: str
    enroll_token: str
    version: Optional[str] = None

@app.post("/agent/enroll")
def agent_enroll(req: EnrollReq):
    if not verify_enroll_token(req.enroll_token, req.source_id):
        raise HTTPException(403, "invalid or expired token")
    agent_id = new_id("agt")
    AGENTS[agent_id] = {"agent_id": agent_id, "source_id": req.source_id, "status": "online", "version": req.version or "0.1.0", "last_seen": _now()}
    SOURCES[req.source_id]["status"] = "online"
    SOURCES[req.source_id]["agent_id"] = agent_id
    SOURCES[req.source_id]["last_seen"] = _now()
    return {"agent_id": agent_id, "poll_url": "/agent/jobs/next", "heartbeat_url": "/agent/heartbeat"}

class HeartbeatReq(BaseModel):
    agent_id: str
    caps: Dict[str, Any] = {}
    summary: Dict[str, Any] = {}

@app.post("/agent/heartbeat")
def agent_heartbeat(req: HeartbeatReq):
    ag = AGENTS.get(req.agent_id)
    if not ag: raise HTTPException(404, "unknown agent")
    ag["last_seen"] = _now()
    ag["caps"] = req.caps
    ag["summary"] = req.summary
    src = SOURCES.get(ag["source_id"])
    if src:
        src["last_seen"] = _now()
        src["status"] = "online"
    return {"ok": True}

@app.get("/agent/jobs/next")
def agent_jobs_next(agent_id: str):
    inbox = AGENT_INBOX.get(agent_id, [])
    if not inbox:
        return {"job": None}
    job_id = inbox.pop(0)
    job = JOBS.get(job_id)
    if not job: return {"job": None}
    job["status"] = "running"
    job["progress"] = {"phase": "started", "pct": 5}
    return {"job": {"job_id": job_id, "kind": job["kind"]}}

class ChunkReq(BaseModel):
    data_type: str
    payload: Dict[str, Any]

@app.post("/agent/jobs/{job_id}/chunk")
def job_chunk(job_id: str, req: ChunkReq):
    job = JOBS.get(job_id)
    if not job: raise HTTPException(404, "job not found")
    job["chunks"].append({"t": _now(), "type": req.data_type, "payload": req.payload})
    # naive progress bump
    job["progress"]["pct"] = min(95, job["progress"]["pct"] + 10)
    job["progress"]["phase"] = req.data_type
    return {"ok": True}

@app.post("/agent/jobs/{job_id}/done")
def job_done(job_id: str, ok: bool = Body(True)):
    job = JOBS.get(job_id)
    if not job: raise HTTPException(404, "job not found")
    job["status"] = "done" if ok else "failed"
    job["progress"] = {"phase": "complete" if ok else "failed", "pct": 100 if ok else job["progress"]["pct"]}
    # Normalize + run planner (very simple: convert host facts to a web-app guess later)
    return {"ok": True, "status": job["status"]}

# ---------------- Serve installer stubs ----------------
from fastapi.responses import PlainTextResponse

@app.get("/agent/install.sh", response_class=PlainTextResponse)
def install_sh():
    return INSTALL_SH

@app.get("/agent/install.ps1", response_class=PlainTextResponse)
def install_ps1():
    return INSTALL_PS1

# ---------------- Installer script content ----------------
INSTALL_SH = r"""#!/usr/bin/env bash
# Minimal installer: writes config & systemd unit; expects youragent binary at /usr/local/bin/youragent
set -euo pipefail
API="http://localhost:8080"
SOURCE_ID=""
ENROLL_TOKEN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --api) API="$2"; shift 2;;
    --source-id) SOURCE_ID="$2"; shift 2;;
    --enroll-token) ENROLL_TOKEN="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done
if [[ -z "$SOURCE_ID" || -z "$ENROLL_TOKEN" ]]; then
  echo "Usage: install.sh --api http://host:8080 --source-id <id> --enroll-token <token>"
  exit 1
fi
sudo mkdir -p /etc/youragent
cat | sudo tee /etc/youragent/config.yaml >/dev/null <<EOF
api: "$API"
source_id: "$SOURCE_ID"
enroll_token: "$ENROLL_TOKEN"
EOF

# systemd unit
cat | sudo tee /etc/systemd/system/youragent.service >/dev/null <<'EOF'
[Unit]
Description=YourAgent VM scanner
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/usr/local/bin/youragent --config /etc/youragent/config.yaml
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
if [[ ! -x /usr/local/bin/youragent ]]; then
  echo "NOTE: /usr/local/bin/youragent not found. Build/copy the agent binary there, then run:"
  echo "  sudo systemctl enable --now youragent"
  exit 0
fi
sudo systemctl enable --now youragent
echo "Installed. Status:"
systemctl status youragent --no-pager
"""

INSTALL_PS1 = r"""param(
  [string]$Api = "http://localhost:8080",
  [string]$SourceId,
  [string]$EnrollToken
)
if (-not $SourceId -or -not $EnrollToken) {
  Write-Host "Usage: Install-Agent -Api http://host:8080 -SourceId <id> -EnrollToken <token>"
  function Install-Agent {} # shim to allow 'iex' definition
  return
}
$root = "$Env:ProgramData\YourAgent"
New-Item -Force -Type Directory $root | Out-Null
@"
api: '$Api'
source_id: '$SourceId'
enroll_token: '$EnrollToken'
"@ | Out-File -Encoding utf8 "$root\config.yaml"

# Create Windows service that runs C:\Program Files\YourAgent\youragent.exe --config %ProgramData%\YourAgent\config.yaml
$bin = "C:\Program Files\YourAgent\youragent.exe"
if (-Not (Test-Path $bin)) {
  Write-Host "NOTE: $bin not found. Copy the agent binary there, then run: Start-Service YourAgent"
  function Install-Agent {} # shim end
  return
}
New-Service -Name "YourAgent" -BinaryPathName "`"$bin`" --config `"$root\config.yaml`"" -DisplayName "YourAgent VM scanner" -StartupType Automatic -ErrorAction SilentlyContinue
Start-Service YourAgent
function Install-Agent {} # shim end
"""