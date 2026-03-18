#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# AuraScript — One-command Linode Ubuntu 22.04 VPS setup
#
# Usage (as root or with sudo):
#   curl -sSL https://raw.githubusercontent.com/anoop-au/aurascript-dev/main/aurascript/scripts/setup_linode.sh | bash
#
# What this does:
#   1. System update
#   2. Install: Docker, Docker Compose, Nginx, Certbot, Git, UFW
#   3. Configure UFW firewall
#   4. Clone the GitHub repo
#   5. Copy .env.example → .env
#   6. Start Docker containers
#   7. Enable and configure Nginx
#   8. Print post-setup checklist
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="https://github.com/anoop-au/aurascript-dev.git"
APP_DIR="/opt/aurascript"
NGINX_CONF="/etc/nginx/sites-available/aurascript"

# Colours
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || error "Run this script as root or with sudo."

# ── 1. System update ───────────────────────────────────────────────────────────
info "Updating system packages..."
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release ufw git nginx certbot python3-certbot-nginx

# ── 2. Install Docker ──────────────────────────────────────────────────────────
info "Installing Docker..."
if ! command -v docker &>/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    info "Docker installed."
else
    info "Docker already installed — skipping."
fi

# ── 3. Install Docker Compose standalone ──────────────────────────────────────
if ! command -v docker-compose &>/dev/null; then
    info "Installing Docker Compose..."
    COMPOSE_VER="v2.27.0"
    curl -fsSL \
        "https://github.com/docker/compose/releases/download/${COMPOSE_VER}/docker-compose-$(uname -s)-$(uname -m)" \
        -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
fi

# ── 4. UFW firewall ────────────────────────────────────────────────────────────
info "Configuring UFW firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    comment "SSH"
ufw allow 80/tcp    comment "HTTP"
ufw allow 443/tcp   comment "HTTPS"
ufw --force enable
info "UFW enabled: 22 (SSH), 80 (HTTP), 443 (HTTPS) allowed."

# ── 5. Clone repository ────────────────────────────────────────────────────────
info "Cloning AuraScript repository..."
if [ -d "$APP_DIR" ]; then
    warn "$APP_DIR already exists. Pulling latest changes..."
    git -C "$APP_DIR" pull --ff-only
else
    git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ── 6. Create .env from example ───────────────────────────────────────────────
if [ ! -f "$APP_DIR/aurascript/.env" ]; then
    cp "$APP_DIR/aurascript/.env.example" "$APP_DIR/aurascript/.env"
    warn "Copied .env.example → aurascript/.env"
    warn "IMPORTANT: Edit $APP_DIR/aurascript/.env and fill in all required values before starting the service."
else
    info ".env already exists — not overwriting."
fi

# ── 7. Create secrets directory ───────────────────────────────────────────────
mkdir -p /opt/aurascript/secrets
chmod 700 /opt/aurascript/secrets
info "Created /opt/aurascript/secrets — place your GCP service account JSON here."

# ── 8. Configure Nginx ────────────────────────────────────────────────────────
info "Configuring Nginx..."
cp "$APP_DIR/aurascript/nginx/aurascript.conf" "$NGINX_CONF"
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/aurascript
rm -f /etc/nginx/sites-enabled/default

nginx -t && systemctl enable --now nginx
info "Nginx configured and running."

# ── 9. Start Docker containers ────────────────────────────────────────────────
info "Building and starting Docker containers..."
cd "$APP_DIR"
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
info "Containers started."

# ── 10. Post-setup checklist ──────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN} AuraScript setup complete!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
echo ""
echo "  NEXT STEPS (complete in this order):"
echo ""
echo "  1. Edit $APP_DIR/aurascript/.env"
echo "     Fill in: VALID_API_KEYS, WEBHOOK_SECRET, GOOGLE_CLOUD_PROJECT,"
echo "              GOOGLE_APPLICATION_CREDENTIALS, and all other required vars."
echo ""
echo "  2. Place your GCP service account JSON at:"
echo "     /opt/aurascript/secrets/service-account.json"
echo ""
echo "  3. Point DNS records for both domains to this server's IP:"
echo "     www.aurascript.au    → $(curl -s ifconfig.me 2>/dev/null || echo '<your-linode-ip>')"
echo "     www.aurascript.store → (same IP)"
echo ""
echo "  4. Run Certbot SSL once DNS has propagated:"
echo "     certbot --nginx -d www.aurascript.au -d aurascript.au \\"
echo "             -d www.aurascript.store -d aurascript.store"
echo ""
echo "  5. Restart containers after filling .env:"
echo "     cd $APP_DIR && docker-compose -f docker-compose.yml -f docker-compose.prod.yml restart"
echo ""
echo "  6. Verify health:"
echo "     curl https://www.aurascript.au/health"
echo ""
echo "  7. Add GitHub Secrets for CI/CD:"
echo "     LINODE_HOST        — Your Linode IP"
echo "     LINODE_SSH_KEY     — Private key for SSH access"
echo "     LINODE_USER        — SSH user (e.g. root)"
echo ""
