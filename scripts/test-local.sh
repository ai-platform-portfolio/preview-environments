#!/bin/sh
# Run only against this repository's disposable Compose fixture.
set -eu
cd "$(dirname "$0")/.."
./scripts/local-env.sh

docker compose up --build -d --wait

docker compose exec -T api python - < tests/integration.py
seeded_id=$(docker compose exec -T api python - seed < tests/integration.py)
docker compose run --rm migrate

docker compose restart api
docker compose up -d --wait api frontend
docker compose exec -T api python - verify "$seeded_id" < tests/integration.py

# Restore the database even if an outage assertion fails.
trap 'docker compose start db >/dev/null' EXIT HUP INT TERM
docker compose stop db
docker compose exec -T api python - unavailable < tests/integration.py
docker compose start db
docker compose up -d --wait api frontend
trap - EXIT HUP INT TERM

cd frontend
npm ci
npm run build
npm test
