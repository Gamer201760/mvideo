#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
set -a
source /opt/hackathon/ai.env
set +a

: "${OPENAI_API_KEY:?OPENAI_API_KEY is required}"
: "${OPENAI_BASE_URL:?OPENAI_BASE_URL is required}"

export FRONTEND_PORT="${FRONTEND_PORT:-8000}"
export BACKEND_PORT="${BACKEND_PORT:-8001}"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-mvideo-hackathon}"
export GATEWAY_MODEL="${GATEWAY_MODEL:-${OPENAI_MODEL:-ai-sage/GigaChat3.5-432B-A28B-Reasoning}}"

docker compose --env-file /dev/null up --build --detach --wait --wait-timeout 180
curl --fail --silent --show-error "http://127.0.0.1:${FRONTEND_PORT}/api/v1/ready"
