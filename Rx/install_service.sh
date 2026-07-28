#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
sudo install -m 0644 "$ROOT/systemd/gaussianobject-rx.service" /etc/systemd/system/gaussianobject-rx.service
sudo install -m 0755 "$ROOT/bin/Rx" /usr/local/bin/Rx
sudo install -m 0755 "$ROOT/bin/rx-login-prompt" /etc/profile.d/gaussianobject-rx-prompt.sh
sudo systemctl daemon-reload
echo "Installed. Run: Rx on"
echo "The first interactive WSL terminal in each boot will ask whether Rx should stay on."
