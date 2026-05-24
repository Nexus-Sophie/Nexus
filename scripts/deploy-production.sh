#!/usr/bin/env bash
set -euo pipefail

compose_file="${COMPOSE_FILE:-docker-compose.production.yml}"
env_file="${ENV_FILE:-.env.production}"
wait_timeout="${COMPOSE_WAIT_TIMEOUT:-600}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file. Copy .env.production.example and fill in production secrets." >&2
  exit 1
fi

docker compose --env-file "$env_file" -f "$compose_file" pull --ignore-buildable
docker compose --env-file "$env_file" -f "$compose_file" build --pull
docker compose --env-file "$env_file" -f "$compose_file" up -d --remove-orphans --wait --wait-timeout "$wait_timeout"
docker compose --env-file "$env_file" -f "$compose_file" ps
