# Scanner + Agent (MVP)

- **FastAPI** backend:
  - URL scanner (`POST /scan`)
  - Agent control plane: enroll, heartbeat, queue jobs, stream results
  - One-liner installers served at `/agent/install.sh` and `/agent/install.ps1`
- **Go Agent** (Linux, demo):
  - Enroll with token, heartbeat, poll jobs
  - Execute `host_inventory` scan: packages/services/ports/runtimes
- **Frontend** (single page):
  - Tab 1: URL scanner (with plan + diagram + IaC files)
  - Tab 2: Agent wizard (create source, installer commands, scan now, watch status)

## Run backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8080
```

## Frontend
Open `frontend/index.html` in your browser. Keep API base `http://localhost:8080`.

## Build Agent (Linux)
```bash
cd agent
# requires Go 1.20+
GOOS=linux GOARCH=amd64 go build -o youragent main.go
# copy to VM and install:
scp youragent user@vm:/tmp/
ssh user@vm 'sudo install -m 0755 /tmp/youragent /usr/local/bin/youragent'
# on the VM, run the installer printed by the UI:
#   curl -fsSL http://<your-mac-ip>:8080/agent/install.sh | sudo bash -s -- --api http://<your-mac-ip>:8080 --source-id <id> --enroll-token <token>
```

## Local demo on Linux VM
1) Create Source in UI → copy installer.
2) On VM: run installer (it writes config + systemd unit). If the binary is missing, copy `youragent` first and re-run `systemctl enable --now youragent`.
3) Back in UI: click **Scan Now**, watch progress.