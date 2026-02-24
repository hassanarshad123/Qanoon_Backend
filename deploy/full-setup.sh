#!/usr/bin/env bash
set -euo pipefail

info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[OK]\033[0m    $*"; }
err()   { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; }

if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash /tmp/full-setup.sh"
    exit 1
fi

APP_HOME="/home/qanoonai"
BACKEND_DIR="${APP_HOME}/backend"
REPO_DIR="/tmp/qanoonai"

if [[ ! -d "${REPO_DIR}/backend/app" ]]; then
    err "Repo not found at ${REPO_DIR}. Clone it first:"
    err "  cd /tmp && git clone https://github.com/hassanarshad123/Qanoon_Ai_Landing_Page_updated.git qanoonai"
    exit 1
fi

info "Starting QanoonAI full setup..."

# 1. SYSTEM PACKAGES
info "Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3.12 python3.12-venv python3.12-dev nginx certbot python3-certbot-nginx git build-essential
ok "System packages installed."

# 2. CREATE USER
if id "qanoonai" &>/dev/null; then
    info "User 'qanoonai' already exists."
else
    info "Creating system user 'qanoonai'..."
    useradd --system --create-home --shell /usr/sbin/nologin qanoonai
    ok "User created."
fi

# 3. COPY BACKEND CODE
info "Copying backend code..."
mkdir -p "${BACKEND_DIR}"
cp -r "${REPO_DIR}/backend/app"              "${BACKEND_DIR}/"
cp    "${REPO_DIR}/backend/requirements.txt" "${BACKEND_DIR}/"
cp    "${REPO_DIR}/backend/gunicorn.conf.py" "${BACKEND_DIR}/"
cp -r "${REPO_DIR}/backend/deploy"           "${BACKEND_DIR}/"
if [[ -f "${REPO_DIR}/backend/.env.example" ]]; then
    cp "${REPO_DIR}/backend/.env.example" "${BACKEND_DIR}/.env.example"
fi
chown -R qanoonai:qanoonai "${APP_HOME}"
ok "Backend code copied."

# 4. PYTHON VENV + DEPENDENCIES
info "Creating Python virtual environment..."
sudo -u qanoonai python3.12 -m venv "${BACKEND_DIR}/venv"
info "Installing Python dependencies (takes ~60 seconds)..."
sudo -u qanoonai "${BACKEND_DIR}/venv/bin/pip" install --quiet --upgrade pip
sudo -u qanoonai "${BACKEND_DIR}/venv/bin/pip" install --quiet -r "${BACKEND_DIR}/requirements.txt"
ok "Python environment ready."

# 5. CREATE .env TEMPLATE
if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
    info "Creating .env template..."
    cat > "${BACKEND_DIR}/.env" << 'ENVFILE'
# === Required ===
DATABASE_URL=postgresql://user:pass@host/dbname
AUTH_SECRET=your-nextauth-secret-here
ANTHROPIC_API_KEY=sk-ant-...

# === Optional ===
VOYAGE_API_KEY=pa-...
UPSTASH_REDIS_REST_URL=https://....upstash.io
UPSTASH_REDIS_REST_TOKEN=...

# SMTP
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASS=...
SMTP_FROM=noreply@qanoon.ai

# AWS S3
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_S3_BUCKET=qanoonai-uploads
AWS_S3_REGION=ap-south-1

# CORS
CORS_ORIGINS=http://localhost:3000
ENVFILE
    chown qanoonai:qanoonai "${BACKEND_DIR}/.env"
    chmod 600 "${BACKEND_DIR}/.env"
    ok ".env template created. YOU MUST EDIT IT with real values."
else
    info ".env already exists, skipping."
fi

# 6. NGINX CONFIG
info "Configuring nginx..."
cat > /etc/nginx/sites-available/qanoonai << 'NGINXCONF'
limit_req_zone $binary_remote_addr zone=auth_limit:10m rate=10r/s;

upstream qanoonai_backend {
    server 127.0.0.1:8000;
    keepalive 16;
}

server {
    listen 80;
    server_name _;

    location ~ ^/api/v1/auth/(login|register|forgot-password) {
        limit_req zone=auth_limit burst=20 nodelay;
        proxy_pass http://qanoonai_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location ~ ^/api/v1/(briefs|judgments|research)/.*/(generate|stream) {
        proxy_pass http://qanoonai_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_cache off;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }

    location /api/v1/ {
        proxy_pass http://qanoonai_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    location / {
        return 404;
    }

    access_log /var/log/nginx/qanoonai_access.log;
    error_log  /var/log/nginx/qanoonai_error.log;
}
NGINXCONF

rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/qanoonai /etc/nginx/sites-enabled/qanoonai
nginx -t
systemctl restart nginx
ok "Nginx configured and running."

# 7. SYSTEMD SERVICE
info "Installing systemd service..."
cat > /etc/systemd/system/qanoonai.service << 'SYSTEMDUNIT'
[Unit]
Description=QanoonAI FastAPI Backend
After=network.target
Wants=network-online.target

[Service]
Type=notify
User=qanoonai
Group=qanoonai
WorkingDirectory=/home/qanoonai/backend
EnvironmentFile=/home/qanoonai/backend/.env
ExecStart=/home/qanoonai/backend/venv/bin/gunicorn app.main:app -c gunicorn.conf.py
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5
ProtectSystem=strict
ProtectHome=read-only
NoNewPrivileges=true
PrivateTmp=true
ReadWritePaths=/home/qanoonai/backend
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SYSTEMDUNIT

systemctl daemon-reload
systemctl enable qanoonai
ok "Systemd service installed."

# DONE
echo ""
echo "=============================================="
echo "  SETUP COMPLETE"
echo "=============================================="
echo ""
echo "  1. EDIT .env:   sudo nano /home/qanoonai/backend/.env"
echo "  2. START:       sudo systemctl start qanoonai"
echo "  3. STATUS:      sudo systemctl status qanoonai"
echo "  4. LOGS:        sudo journalctl -u qanoonai -f"
echo "  5. TEST:        curl http://localhost:8000/api/v1/health"
echo ""
