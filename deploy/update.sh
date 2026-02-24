#!/usr/bin/env bash
# ============================================================================
# QanoonAI Backend — Zero-Downtime Deploy Script
# ============================================================================
#
# Run this on the EC2 instance after pushing new code:
#
#   ssh -i key.pem ubuntu@<ip> 'sudo /home/qanoonai/backend/deploy/update.sh'
#
# What it does:
#   1. Pulls latest code from git
#   2. Installs any new Python dependencies
#   3. Gracefully reloads gunicorn (SIGHUP → zero downtime)
#
# Gunicorn's graceful reload:
#   - Spawns new workers with updated code
#   - Old workers finish their in-progress requests (including SSE streams)
#   - Old workers then shut down
#   - At no point are requests dropped
#
# ============================================================================

set -euo pipefail

info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
err()   { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

APP_HOME="/home/qanoonai"
BACKEND_DIR="${APP_HOME}/backend"

# --- Must run as root (for systemctl) ---
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (use sudo)."
    exit 1
fi

info "Starting QanoonAI backend update..."

# ============================================================================
# 1. Pull latest code
# ============================================================================
info "Pulling latest code..."
cd "${BACKEND_DIR}"
sudo -u qanoonai git pull --ff-only

ok "Code updated."

# ============================================================================
# 2. Install/update Python dependencies
# ============================================================================
info "Installing Python dependencies..."
sudo -u qanoonai "${BACKEND_DIR}/venv/bin/pip" install --quiet -r "${BACKEND_DIR}/requirements.txt"

ok "Dependencies up to date."

# ============================================================================
# 3. Graceful reload (zero downtime)
# ============================================================================
info "Reloading gunicorn (zero downtime)..."
systemctl reload qanoonai

ok "Reload complete."

# ============================================================================
# 4. Verify
# ============================================================================
sleep 2
if systemctl is-active --quiet qanoonai; then
    ok "Service is running."
else
    err "Service is NOT running! Check: sudo journalctl -u qanoonai -n 50"
    exit 1
fi

echo ""
ok "Deploy complete. Verify: curl https://api.yourdomain.com/api/v1/health"
