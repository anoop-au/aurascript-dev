#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# AuraScript — Zero-downtime deploy script
#
# Called by GitHub Actions after SSH into the Linode VPS:
#   bash /opt/aurascript/aurascript/scripts/deploy.sh [GIT_SHA]
#
# What this does:
#   1. Pull latest code from GitHub
#   2. Re-build Docker image (layer-cached; only changed layers rebuild)
#   3. Rolling restart (stop → start keeps named volume intact)
#   4. Run healthcheck
#   5. Prune dangling images
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="/opt/aurascript"
COMPOSE="docker-compose -f ${APP_DIR}/docker-compose.yml -f ${APP_DIR}/docker-compose.prod.yml"
HEALTH_URL="http://localhost:8080/health"
DEPLOY_TIMEOUT=120   # seconds to wait for healthy response

# Colours
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[DEPLOY]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[DEPLOY]${NC}  $*"; }
error() { echo -e "${RED}[DEPLOY]${NC} $*" >&2; exit 1; }

GIT_SHA="${1:-HEAD}"
info "Starting deploy — target SHA: ${GIT_SHA}"

# ── 1. Pull latest code ────────────────────────────────────────────────────────
info "Pulling latest code from origin..."
cd "${APP_DIR}"
git fetch --all --prune
git checkout --force "${GIT_SHA}"
info "Checked out ${GIT_SHA}."

# ── 2. Build Docker image ──────────────────────────────────────────────────────
info "Building Docker image (cached layers)..."
${COMPOSE} build --pull
info "Build complete."

# ── 3. Rolling restart ─────────────────────────────────────────────────────────
info "Restarting containers..."
${COMPOSE} up -d --remove-orphans
info "Containers restarted."

# ── 4. Wait for healthy response ───────────────────────────────────────────────
info "Waiting for health endpoint (timeout ${DEPLOY_TIMEOUT}s)..."
elapsed=0
while true; do
    if curl -sf "${HEALTH_URL}" > /dev/null 2>&1; then
        info "Health check passed after ${elapsed}s."
        break
    fi
    if [ "${elapsed}" -ge "${DEPLOY_TIMEOUT}" ]; then
        error "Health check timed out after ${DEPLOY_TIMEOUT}s — rolling back may be needed."
    fi
    sleep 5
    elapsed=$((elapsed + 5))
done

# ── 5. Prune dangling images (keep disk usage low) ─────────────────────────────
info "Pruning dangling Docker images..."
docker image prune -f

info "Deploy complete — running SHA: ${GIT_SHA}"
