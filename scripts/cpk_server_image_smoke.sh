#!/bin/sh
set -eu

IMAGE="${CPK_SERVER_IMAGE:-control-plane-kit-servers-cpk-server:local}"
CONTAINER=""
LABEL="org.openj92.project=control-plane-kit-servers"

cleanup() {
  if [ -n "$CONTAINER" ]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

docker build -f products/cpk_server/Dockerfile -t "$IMAGE" .

if docker run --rm "$IMAGE" >/tmp/cpk-server-missing-config.out 2>&1; then
  echo "cpk-server started without required configuration" >&2
  exit 1
fi

docker inspect "$IMAGE" --format '{{.Config.User}}' | grep -q '^cpk$'

CONTAINER="$(docker run -d \
  --label "$LABEL" \
  -p 127.0.0.1::8080 \
  -e CPK_SERVER_MODE=execution-capable \
  -e CPK_CONTROL_AUTH_CONFIGURED=true \
  -e CPK_PORT=8080 \
  "$IMAGE")"

PORT="$(docker port "$CONTAINER" 8080/tcp | sed 's/.*://')"
BASE="http://127.0.0.1:$PORT"

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "$BASE/health/live" >/tmp/cpk-server-live.json 2>/dev/null; then
    break
  fi
  sleep 1
done

curl -fsS "$BASE/health/live" | grep -q '"live"'
curl -fsS "$BASE/health/ready" | grep -q '"ready"'

unauthorized_status="$(curl -sS -o /tmp/cpk-server-unauthorized.json -w '%{http_code}' \
  "$BASE/workspaces/workspace-a/graphs/current")"
[ "$unauthorized_status" = "401" ]

authorized_read="$(curl -fsS \
  -H 'Authorization: Bearer present' \
  "$BASE/workspaces/workspace-a/graphs/current")"
printf '%s' "$authorized_read" | grep -q '"service": "reads"'
printf '%s' "$authorized_read" | grep -q '"route_id": "read.current-graph"'

mcp_response="$(curl -fsS \
  -H 'Authorization: Bearer present' \
  -H 'Accept: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H 'Mcp-Method: tools/call' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"call-1","method":"tools/call","params":{"name":"command.deployment.plan","arguments":{"workspace_id":"workspace-a"}}}' \
  "$BASE/mcp")"
printf '%s' "$mcp_response" | grep -q '"service": "planning"'
printf '%s' "$mcp_response" | grep -q '"surface": "mcp"'

cleanup
CONTAINER=""

sh scripts/docker_residue_audit.sh

echo "cpk-server image smoke passed"
