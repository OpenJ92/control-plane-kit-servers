#!/bin/sh
set -eu

IMAGE="${POSTGRES_SERVER_IMAGE:-postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777}"
CONTAINER="cpk-postgres-server-smoke"
VOLUME="cpk-postgres-server-smoke-data"
PASSWORD="${POSTGRES_SERVER_PASSWORD:-cpk-smoke-password}"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker volume rm "$VOLUME" >/dev/null 2>&1 || true
}

trap cleanup EXIT
cleanup

docker volume create \
  --label org.openj92.project=control-plane-kit-servers \
  --label org.openj92.lifecycle=retained-test-data \
  "$VOLUME" >/dev/null

docker run -d \
  --name "$CONTAINER" \
  --label org.openj92.project=control-plane-kit-servers \
  -e POSTGRES_DB=cpk \
  -e POSTGRES_USER=cpk \
  -e POSTGRES_PASSWORD="$PASSWORD" \
  -v "$VOLUME:/var/lib/postgresql/data" \
  "$IMAGE" >/dev/null

tries=0
until docker exec "$CONTAINER" pg_isready -U cpk -d cpk >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -gt 60 ]; then
    echo "postgres did not become ready" >&2
    docker logs "$CONTAINER" >&2 || true
    exit 1
  fi
  sleep 1
done

RESULT="$(docker exec -e PGPASSWORD="$PASSWORD" "$CONTAINER" \
  psql -U cpk -d cpk -tAc "select 1")"
if [ "$RESULT" != "1" ]; then
  echo "unexpected postgres readiness query result: $RESULT" >&2
  exit 1
fi

echo "postgres-server image smoke passed: select $RESULT"
