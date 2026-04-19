#!/usr/bin/env bash
# Migrate data from legacy mongo:7 volume to mongodb-atlas-local.
# Must be run with the OLD docker-compose.yml still pointing to mongo:7.
# After success, swap the image (Task 1) and start the stack again.
set -euo pipefail
: "${MONGO_PASSWORD:?must be set in environment}"

BACKUP=./mongo-backup.archive

echo "==> Dumping from legacy mongo..."
docker compose exec -T mongo mongodump \
  --uri="mongodb://uvo:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
  --archive > "$BACKUP"

echo "==> Stopping stack and preserving legacy volume..."
docker compose down
docker volume create uvo-search_mongo_data_legacy >/dev/null
docker run --rm \
  -v uvo-search_mongo_data:/from \
  -v uvo-search_mongo_data_legacy:/to \
  alpine sh -c 'cd /from && tar cf - . | (cd /to && tar xf -)'
docker volume rm uvo-search_mongo_data

echo "==> Starting fresh mongo (atlas-local) — make sure compose uses the new image..."
docker compose up -d mongo

echo "==> Waiting for mongo to become healthy..."
for i in $(seq 1 30); do
  if docker compose exec -T mongo mongosh --quiet --eval 'db.adminCommand("ping").ok' | grep -q 1; then
    break
  fi
  sleep 2
done

echo "==> Restoring dump..."
docker compose exec -T mongo mongorestore \
  --uri="mongodb://uvo:${MONGO_PASSWORD}@localhost:27017/?authSource=admin" \
  --archive < "$BACKUP"

echo "==> Done. Legacy volume kept as uvo-search_mongo_data_legacy for rollback."
echo "    Remove with: docker volume rm uvo-search_mongo_data_legacy"
