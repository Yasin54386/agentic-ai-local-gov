#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# One-time provisioning for a fresh DigitalOcean droplet (Ubuntu 22.04/24.04).
#
# Run ONCE on the droplet as root (or a sudo user). After this, every push to
# main auto-deploys via .github/workflows/deploy.yml — you never run this again.
#
#   ssh root@YOUR_DROPLET_IP
#   curl -fsSL https://raw.githubusercontent.com/Yasin54386/agentic-ai-local-gov/main/deploy/provision-digitalocean.sh | bash
#
# (or scp it up and `bash provision-digitalocean.sh`)
#
# This sets up the web stack on a small droplet. The AI chat is powered by a
# hosted API — set ANTHROPIC_API_KEY in the environment / .env (see
# deploy/DIGITALOCEAN.md). No model server runs on the droplet.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Yasin54386/agentic-ai-local-gov.git}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/ask-territory}"
SERVER_NAME="${SERVER_NAME:-_}"   # set to your domain, e.g. askterritory.com, or leave _ for IP

echo "==> 1/6  System packages"
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y git python3 python3-pip nginx ca-certificates curl

echo "==> 2/6  Docker + compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo systemctl enable --now docker

echo "==> 3/6  Clone the repo into $DEPLOY_DIR"
if [ ! -d "$DEPLOY_DIR/.git" ]; then
  sudo git clone "$REPO_URL" "$DEPLOY_DIR"
fi
cd "$DEPLOY_DIR"
sudo git fetch origin main
sudo git reset --hard origin/main

echo "==> 4/6  Build the database (schema + seed + committed open data)"
sudo python3 -m db.migrate
sudo python3 -m db.load || echo "  (db.load skipped — seed data from migrations still present)"

# The DB is built as root, but the container runs as appuser (UID 1000) and must
# be able to write the SQLite WAL files. Hand the data dir to that UID.
sudo chown -R 1000:1000 data

echo "==> 5/6  Start the web container (web-only profile, no model)"
sudo docker compose up -d --build --remove-orphans

echo "==> 6/6  nginx reverse proxy on :80  ->  127.0.0.1:8000"
sudo tee /etc/nginx/sites-available/ask-territory >/dev/null <<NGINX
server {
    listen 80;
    server_name ${SERVER_NAME};
    client_max_body_size 1m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/ask-territory /etc/nginx/sites-enabled/ask-territory
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Open the firewall if ufw is active.
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 'Nginx Full' || true
  sudo ufw allow OpenSSH || true
fi

echo
echo "✅ Provisioning complete."
echo "   Visit:  http://$(curl -s ifconfig.me 2>/dev/null || echo YOUR_DROPLET_IP)/"
echo
echo "Next: add these GitHub repo secrets so pushes to main auto-deploy —"
echo "   DO_HOST        = this droplet's public IP"
echo "   DO_USER        = $(whoami)"
echo "   DO_SSH_KEY     = the PRIVATE key whose public half is in ~/.ssh/authorized_keys here"
echo "   DO_DEPLOY_DIR  = $DEPLOY_DIR"
