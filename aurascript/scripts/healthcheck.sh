#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# AuraScript — Post-deploy health verification
#
# Usage:
#   bash healthcheck.sh [BASE_URL]
#   Default BASE_URL: https://www.aurascript.au
#
# Exits 0 if all checks pass, 1 if any check fails.
# Designed to be called from CI/CD after deploy.sh succeeds.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

BASE_URL="${1:-https://www.aurascript.au}"
PASS=0
FAIL=0

# Colours
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}[PASS]${NC} $*"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}[FAIL]${NC} $*"; FAIL=$((FAIL + 1)); }
info() { echo -e "${YELLOW}[INFO]${NC} $*"; }

info "Running health checks against: ${BASE_URL}"
echo ""

# ── Check 1: /health returns 200 ──────────────────────────────────────────────
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/health" 2>/dev/null || echo "000")
if [ "${HTTP_CODE}" = "200" ]; then
    pass "/health → HTTP ${HTTP_CODE}"
else
    fail "/health → HTTP ${HTTP_CODE} (expected 200)"
fi

# ── Check 2: /health returns valid JSON with status ───────────────────────────
BODY=$(curl -sf --max-time 10 "${BASE_URL}/health" 2>/dev/null || echo "")
if echo "${BODY}" | grep -q '"status"'; then
    pass "/health response contains 'status' field"
else
    fail "/health response missing 'status' field — got: ${BODY:0:200}"
fi

# ── Check 3: /health/ready returns 200 ────────────────────────────────────────
READY_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "${BASE_URL}/health/ready" 2>/dev/null || echo "000")
if [ "${READY_CODE}" = "200" ]; then
    pass "/health/ready → HTTP ${READY_CODE}"
else
    fail "/health/ready → HTTP ${READY_CODE} (expected 200)"
fi

# ── Check 4: SSL certificate valid (HTTPS only) ────────────────────────────────
if [[ "${BASE_URL}" == https://* ]]; then
    DOMAIN=$(echo "${BASE_URL}" | sed 's|https://||' | sed 's|/.*||')
    EXPIRY=$(echo | openssl s_client -connect "${DOMAIN}:443" -servername "${DOMAIN}" 2>/dev/null \
        | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || echo "")
    if [ -n "${EXPIRY}" ]; then
        pass "SSL certificate valid — expires: ${EXPIRY}"
    else
        fail "SSL certificate check failed for ${DOMAIN}"
    fi
fi

# ── Check 5: Security headers present ─────────────────────────────────────────
HEADERS=$(curl -sI --max-time 10 "${BASE_URL}/health" 2>/dev/null || echo "")
if echo "${HEADERS}" | grep -qi "strict-transport-security"; then
    pass "HSTS header present"
else
    fail "HSTS header missing"
fi

if echo "${HEADERS}" | grep -qi "x-content-type-options"; then
    pass "X-Content-Type-Options header present"
else
    fail "X-Content-Type-Options header missing"
fi

# ── Check 6: Unauthenticated /transcribe returns 401 (not 500) ────────────────
TRANSCRIBE_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
    -X POST "${BASE_URL}/transcribe" 2>/dev/null || echo "000")
if [ "${TRANSCRIBE_CODE}" = "401" ] || [ "${TRANSCRIBE_CODE}" = "422" ]; then
    pass "/transcribe without auth → HTTP ${TRANSCRIBE_CODE} (auth guard working)"
else
    fail "/transcribe without auth → HTTP ${TRANSCRIBE_CODE} (expected 401 or 422)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
if [ "${FAIL}" -eq 0 ]; then
    echo -e "${GREEN} All ${PASS} checks passed.${NC}"
    echo "══════════════════════════════════════════════"
    exit 0
else
    echo -e "${RED} ${FAIL} check(s) FAILED / ${PASS} passed.${NC}"
    echo "══════════════════════════════════════════════"
    exit 1
fi
