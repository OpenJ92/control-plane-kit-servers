#!/bin/sh
set -eu

IMAGE="${CPK_SERVER_IMAGE:-localhost/control-plane-kit-servers/cpk-server:local}"
BUILD_IMAGE="${CPK_SERVER_BUILD_IMAGE:-1}"
CONTAINER=""
LABEL="org.openj92.project=control-plane-kit-servers"
WORKPLACE_DATABASE_URL="${CPK_WORKPLACE_DATABASE_URL:-postgres://cpk-workplace-smoke.invalid/workplace}"
ACTIVITY_HISTORY_DATABASE_URL="${CPK_ACTIVITY_HISTORY_DATABASE_URL:-postgres://cpk-activity-smoke.invalid/activity}"
OBSERVER_STATE_DATABASE_URL="${CPK_OBSERVER_STATE_DATABASE_URL:-postgres://cpk-observer-smoke.invalid/observer}"
GRAPH_TOPOLOGY_DATABASE_URL="${CPK_GRAPH_TOPOLOGY_DATABASE_URL:-postgres://cpk-graph-smoke.invalid/graph}"

cleanup() {
  if [ -n "$CONTAINER" ]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

if [ "$BUILD_IMAGE" = "1" ]; then
  docker build -f products/cpk_server/Dockerfile -t "$IMAGE" .
fi

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
  -e CPK_WORKPLACE_DATABASE_URL="$WORKPLACE_DATABASE_URL" \
  -e CPK_ACTIVITY_HISTORY_DATABASE_URL="$ACTIVITY_HISTORY_DATABASE_URL" \
  -e CPK_OBSERVER_STATE_DATABASE_URL="$OBSERVER_STATE_DATABASE_URL" \
  -e CPK_GRAPH_TOPOLOGY_DATABASE_URL="$GRAPH_TOPOLOGY_DATABASE_URL" \
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
ready="$(curl -fsS "$BASE/health/ready")"
printf '%s' "$ready" | grep -q '"ready"'
printf '%s' "$ready" | grep -q '"stores": "configured"'
if printf '%s' "$ready" | grep -q 'postgres://'; then
  echo "ready response leaked store endpoint" >&2
  exit 1
fi

unauthorized_status="$(curl -sS -o /tmp/cpk-server-unauthorized.json -w '%{http_code}' \
  "$BASE/workspaces/workspace-a/graphs/current")"
[ "$unauthorized_status" = "401" ]

mcp_unauthorized_status="$(curl -sS -o /tmp/cpk-server-mcp-unauthorized.json -w '%{http_code}' \
  -H 'Accept: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H 'Mcp-Method: tools/call' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"call-unauthorized","method":"tools/call","params":{"name":"command.deployment.plan","arguments":{"workspace_id":"workspace-a"}}}' \
  "$BASE/mcp")"
[ "$mcp_unauthorized_status" = "401" ]

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

mcp_read_response="$(curl -fsS \
  -H 'Authorization: Bearer present' \
  -H 'Accept: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H 'Mcp-Method: resources/read' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"read-1","method":"resources/read","params":{"name":"read.current-graph","arguments":{"workspace_id":"workspace-a"}}}' \
  "$BASE/mcp")"
printf '%s' "$mcp_read_response" | grep -q '"service": "reads"'
printf '%s' "$mcp_read_response" | grep -q '"surface": "mcp"'

cleanup
CONTAINER=""

sh scripts/docker_residue_audit.sh

echo "cpk-server image smoke passed"
