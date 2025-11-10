#!/usr/bin/env bash
# helper script that copies a local binary and installs service (for lab/demo)
set -euo pipefail
BIN="${1:-./youragent}"
if [[ ! -f "$BIN" ]]; then echo "Usage: ./install_local.sh ./youragent"; exit 1; fi
sudo install -m 0755 "$BIN" /usr/local/bin/youragent
echo "Binary installed to /usr/local/bin/youragent"
echo "Now run the network installer to write config & systemd unit:"
echo "  curl -fsSL http://localhost:8080/agent/install.sh | sudo bash -s -- --api http://localhost:8080 --source-id <id> --enroll-token <token>"