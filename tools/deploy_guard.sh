#!/usr/bin/env bash
set -euo pipefail

# PostBandit deploy guard:
# - Validates core containers are running
# - Validates frontend runtime API/auth env values
# - Validates backend health
# - Validates public API CORS for app origin

APP_DOMAIN="${APP_DOMAIN:-https://postbandit.com}"
API_DOMAIN="${API_DOMAIN:-https://api.postbandit.com}"

EXPECTED_NEXTAUTH_URL="${EXPECTED_NEXTAUTH_URL:-$APP_DOMAIN}"
EXPECTED_NEXT_PUBLIC_API_URL="${EXPECTED_NEXT_PUBLIC_API_URL:-$API_DOMAIN}"
EXPECTED_INTERNAL_API_URL="${EXPECTED_INTERNAL_API_URL:-http://backend:8000}"

echo "[deploy-guard] app domain: $APP_DOMAIN"
echo "[deploy-guard] api domain: $API_DOMAIN"

if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy-guard] ERROR: docker is required"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "[deploy-guard] ERROR: curl is required"
  exit 1
fi

required_services=(backend frontend worker)
for service in "${required_services[@]}"; do
  if ! docker compose ps "$service" >/dev/null 2>&1; then
    echo "[deploy-guard] ERROR: service '$service' not found in docker compose"
    exit 1
  fi
done

echo "[deploy-guard] checking service status..."
for service in "${required_services[@]}"; do
  status="$(docker compose ps --format json "$service" | python3 -c 'import json,sys; d=json.load(sys.stdin); row=d[0] if isinstance(d,list) and d else (d if isinstance(d,dict) else {}); print((row.get("State") or row.get("Status") or "").strip().lower())')"
  if [[ "$status" != "running" ]]; then
    echo "[deploy-guard] ERROR: service '$service' state is '$status' (expected 'running')"
    docker compose ps
    exit 1
  fi
done

frontend_container="$(docker compose ps --format json frontend | python3 -c 'import json,sys; d=json.load(sys.stdin); row=d[0] if isinstance(d,list) and d else (d if isinstance(d,dict) else {}); print((row.get("Name") or "").strip())')"
if [[ -z "$frontend_container" ]]; then
  echo "[deploy-guard] ERROR: could not resolve frontend container name"
  exit 1
fi

echo "[deploy-guard] checking frontend runtime env..."
env_dump="$(docker exec "$frontend_container" sh -lc 'printenv | grep -E "^(NEXTAUTH_URL|NEXT_PUBLIC_API_URL|INTERNAL_API_URL)="')"
echo "$env_dump"

actual_nextauth_url="$(printf "%s\n" "$env_dump" | sed -n 's/^NEXTAUTH_URL=//p')"
actual_next_public_api_url="$(printf "%s\n" "$env_dump" | sed -n 's/^NEXT_PUBLIC_API_URL=//p')"
actual_internal_api_url="$(printf "%s\n" "$env_dump" | sed -n 's/^INTERNAL_API_URL=//p')"

if [[ "$actual_nextauth_url" != "$EXPECTED_NEXTAUTH_URL" ]]; then
  echo "[deploy-guard] ERROR: NEXTAUTH_URL mismatch: got '$actual_nextauth_url' expected '$EXPECTED_NEXTAUTH_URL'"
  exit 1
fi

if [[ "$actual_next_public_api_url" != "$EXPECTED_NEXT_PUBLIC_API_URL" ]]; then
  echo "[deploy-guard] ERROR: NEXT_PUBLIC_API_URL mismatch: got '$actual_next_public_api_url' expected '$EXPECTED_NEXT_PUBLIC_API_URL'"
  exit 1
fi

if [[ "$actual_internal_api_url" != "$EXPECTED_INTERNAL_API_URL" ]]; then
  echo "[deploy-guard] ERROR: INTERNAL_API_URL mismatch: got '$actual_internal_api_url' expected '$EXPECTED_INTERNAL_API_URL'"
  exit 1
fi

echo "[deploy-guard] checking backend health..."
health_json="$(curl -fsS http://127.0.0.1:8000/health)"
echo "$health_json"

echo "[deploy-guard] checking public API CORS..."
cors_headers="$(curl -fsSI \
  -H "Origin: $APP_DOMAIN" \
  -H "Access-Control-Request-Method: GET" \
  -X OPTIONS "$API_DOMAIN/api/videos")"
echo "$cors_headers" | grep -iq "access-control-allow-origin: $APP_DOMAIN" || {
  echo "[deploy-guard] ERROR: missing/incorrect Access-Control-Allow-Origin for $APP_DOMAIN"
  exit 1
}
echo "$cors_headers" | grep -iq "access-control-allow-credentials: true" || {
  echo "[deploy-guard] ERROR: missing Access-Control-Allow-Credentials: true"
  exit 1
}

echo "[deploy-guard] checking public API auth response shape..."
http_code="$(curl -s -o /tmp/deploy_guard_videos_body.txt -w "%{http_code}" "$API_DOMAIN/api/videos?limit=1&offset=0")"
if [[ "$http_code" != "401" && "$http_code" != "403" ]]; then
  body_preview="$(head -c 200 /tmp/deploy_guard_videos_body.txt || true)"
  echo "[deploy-guard] ERROR: expected 401/403 from unauthenticated /api/videos, got $http_code"
  echo "[deploy-guard] body preview: $body_preview"
  exit 1
fi

echo "[deploy-guard] PASS"
