#!/usr/bin/env bash
# deploy.sh — build and deploy LayaKBTest backend and/or frontend
#
# Usage:
#   ./scripts/deploy.sh backend    # rebuild Docker image and restart Container App
#   ./scripts/deploy.sh frontend   # build React app and publish to Static Web Apps
#   ./scripts/deploy.sh all        # both
#
# Requirements: az CLI logged in, terraform applied, npx available

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra"

# ── Read outputs from Terraform ───────────────────────────────────────────────
echo "Reading Terraform outputs..."
cd "$INFRA_DIR"

ACR_LOGIN_SERVER=$(terraform output -raw acr_login_server)
API_URL=$(terraform output -raw api_url)
FRONTEND_URL=$(terraform output -raw frontend_url)
SWA_API_KEY=$(terraform output -raw swa_api_key)
RESOURCE_GROUP=$(terraform output -raw resource_group_name)

# Derive Container App name from API URL (ca-<name>.<domain>)
CONTAINER_APP_NAME=$(echo "$API_URL" | sed 's|https://||' | cut -d'.' -f1)
ACR_NAME=$(echo "$ACR_LOGIN_SERVER" | cut -d'.' -f1)

echo "  ACR:            $ACR_LOGIN_SERVER"
echo "  Container App:  $CONTAINER_APP_NAME"
echo "  API URL:        $API_URL"
echo "  Frontend URL:   $FRONTEND_URL"

# ── Deploy backend ────────────────────────────────────────────────────────────
deploy_backend() {
  echo ""
  echo "==> Building backend image via ACR (linux/amd64)..."
  cd "$REPO_ROOT"
  az acr build \
    --registry "$ACR_NAME" \
    --image layakb-api:latest \
    --platform linux/amd64 \
    ./backend

  echo "==> Restarting Container App to pull new image..."
  az containerapp update \
    --name "$CONTAINER_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "${ACR_LOGIN_SERVER}/layakb-api:latest" \
    --output none

  echo "==> Waiting for backend to become healthy..."
  for i in $(seq 1 12); do
    STATUS=$(curl -sf "$API_URL/api/health" 2>/dev/null || true)
    if echo "$STATUS" | grep -q '"ok"'; then
      echo "    Backend healthy: $STATUS"
      break
    fi
    echo "    Attempt $i/12 — not ready yet, retrying in 10s..."
    sleep 10
  done
}

# ── Deploy frontend ───────────────────────────────────────────────────────────
deploy_frontend() {
  echo ""
  echo "==> Building frontend (VITE_API_BASE_URL=$API_URL)..."
  cd "$REPO_ROOT/frontend"
  VITE_API_BASE_URL="$API_URL" npm run build

  echo "==> Deploying to Azure Static Web Apps..."
  npx @azure/static-web-apps-cli deploy ./dist \
    --deployment-token "$SWA_API_KEY" \
    --env production

  echo "    Frontend deployed: $FRONTEND_URL"
}

# ── Entrypoint ────────────────────────────────────────────────────────────────
TARGET="${1:-all}"

case "$TARGET" in
  backend)
    deploy_backend
    ;;
  frontend)
    deploy_frontend
    ;;
  all)
    deploy_backend
    deploy_frontend
    ;;
  *)
    echo "Usage: $0 [backend|frontend|all]"
    exit 1
    ;;
esac

echo ""
echo "Done."
echo "  Frontend: $FRONTEND_URL"
echo "  Backend:  $API_URL"
