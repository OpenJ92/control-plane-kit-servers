#!/bin/sh
set -eu

IMAGE="${CPK_SERVER_IMAGE:-localhost/control-plane-kit-servers/cpk-server:local}"
BUILD_IMAGE="${CPK_SERVER_BUILD_IMAGE:-1}"
PROFILE="${CPK_SERVER_SMOKE_PROFILE:-wrapped-source}"
CONTROL_RECORDS=""
case "$PROFILE" in
  wrapped-source)
    : "${CPK_SERVERS_TEST_IMAGE:?wrapped-source requires the owning test/controller image}"
    ;;
  published-baseline) ;;
  *) echo "cpk-server image smoke: invalid profile" >&2; exit 1 ;;
esac
CONTAINER=""
POSTGRES_CONTAINER=""
NETWORK="cpk-server-smoke-$$"
PHASE="bootstrap"
LABEL="org.openj92.project=control-plane-kit-servers"
MISSING_CONFIG_OUTPUT="/tmp/cpk-server-missing-config-$$.out"
IMPORT_BODY="/tmp/cpk-server-import-product-$$.json"
UNAUTHORIZED_BODY="/tmp/cpk-server-unauthorized-$$.json"
MCP_UNAUTHORIZED_BODY="/tmp/cpk-server-mcp-unauthorized-$$.json"
HOST_CURL_ERROR="/tmp/cpk-server-host-curl-$$.err"
HOST_CURL_ERROR_LIMIT=512
DATABASE_URL="${CPK_DATABASE_URL:-postgresql://cpk:cpk@cpk-postgres:5432/cpk}"
WORKPLACE_DATABASE_URL="${CPK_WORKPLACE_DATABASE_URL:-$DATABASE_URL}"
ACTIVITY_HISTORY_DATABASE_URL="${CPK_ACTIVITY_HISTORY_DATABASE_URL:-$DATABASE_URL}"
OBSERVER_STATE_DATABASE_URL="${CPK_OBSERVER_STATE_DATABASE_URL:-$DATABASE_URL}"
GRAPH_TOPOLOGY_DATABASE_URL="${CPK_GRAPH_TOPOLOGY_DATABASE_URL:-$DATABASE_URL}"
RUNTIME_INTERPRETERS="${CPK_RUNTIME_INTERPRETERS:-none}"
STATIC_WORKSPACE_GRANTS_JSON="${CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON:-{\"workspace-a\":[\"hub:instance:create\",\"instance:workspace:read\",\"instance:workspace:edit\",\"plan:request\"]}}"
HEALTH_ATTEMPTS="${CPK_SERVER_HEALTH_ATTEMPTS:-30}"
REQUEST_HOST="${CPK_SERVER_SMOKE_HOST:-127.0.0.1}"

cleanup_control_fixture() {
  if [ -n "$CONTROL_RECORDS" ]; then
    rm -f "$CONTROL_RECORDS/control.json" "$CONTROL_RECORDS/surface.headers" \
      "$CONTROL_RECORDS/health.headers" "$CONTROL_RECORDS/surface.json" \
      "$CONTROL_RECORDS/health.json" "$CONTROL_RECORDS/denied.json" || return 1
    rmdir "$CONTROL_RECORDS" || return 1
    [ ! -e "$CONTROL_RECORDS" ] || return 1
    CONTROL_RECORDS=""
  fi
}

cleanup() {
  rm -f "$MISSING_CONFIG_OUTPUT" "$IMPORT_BODY" "$UNAUTHORIZED_BODY" \
    "$MCP_UNAUTHORIZED_BODY" "$HOST_CURL_ERROR"
  if [ -n "$CONTAINER" ]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  fi
  if [ -n "$POSTGRES_CONTAINER" ]; then
    docker rm -f "$POSTGRES_CONTAINER" >/dev/null 2>&1 || true
  fi
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}

finish() {
  status=$?
  trap - EXIT INT TERM
  if [ "$status" -ne 0 ]; then
    echo "cpk-server image smoke failed during phase: $PHASE" >&2
    if [ -n "$CONTAINER" ]; then
      echo "cpk-server bounded log tail:" >&2
      docker logs --tail 80 "$CONTAINER" >&2 || true
    fi
    if [ -n "$POSTGRES_CONTAINER" ]; then
      echo "postgres bounded log tail:" >&2
      docker logs --tail 40 "$POSTGRES_CONTAINER" >&2 || true
    fi
  fi
  cleanup
  cleanup_control_fixture || status=1
  exit "$status"
}

phase() {
  PHASE="$1"
  echo "cpk-server image smoke: $PHASE"
}

curl_with_retry() {
  url="$1"
  output=""
  attempt=1
  while [ "$attempt" -le "$HEALTH_ATTEMPTS" ]; do
    if output="$(curl -fsS "$url" 2>/dev/null)"; then
      printf '%s' "$output"
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  return 1
}

internal_liveness_probe() {
  docker exec "$CONTAINER" python -I -c \
'import json,urllib.request
response=urllib.request.urlopen("http://127.0.0.1:8080/health/live",timeout=2)
body=response.read(513)
raise SystemExit(
    0
    if response.status == 200
    and len(body) <= 512
    and json.loads(body) == {"status": "live"}
    else 1
)' >/dev/null 2>&1
}

liveness_with_diagnostics() {
  url="$1"
  output=""
  attempt=1
  HOST_CURL_STATUS=0
  CONTAINER_RUNNING="unknown"
  CONTAINER_EXIT_CODE="unknown"
  CONTAINER_OOM_KILLED="unknown"

  while [ "$attempt" -le "$HEALTH_ATTEMPTS" ]; do
    if output="$(curl --connect-timeout 1 --max-time 2 --fail --silent \
      --show-error "$url" 2>"$HOST_CURL_ERROR")"; then
      printf '%s' "$output"
      return 0
    else
      HOST_CURL_STATUS=$?
    fi

    if ! CONTAINER_STATE="$(docker inspect --format \
      '{{.State.Running}}|{{.State.ExitCode}}|{{.State.OOMKilled}}' \
      "$CONTAINER" 2>/dev/null)"; then
      echo "cpk-server liveness category=container-state-unavailable" >&2
      return 1
    fi
    CONTAINER_RUNNING="${CONTAINER_STATE%%|*}"
    CONTAINER_STATE_REMAINDER="${CONTAINER_STATE#*|}"
    CONTAINER_EXIT_CODE="${CONTAINER_STATE_REMAINDER%%|*}"
    CONTAINER_OOM_KILLED="${CONTAINER_STATE_REMAINDER#*|}"
    case "$CONTAINER_RUNNING" in
      true|false) ;;
      *)
        echo "cpk-server liveness category=container-state-invalid" >&2
        return 1
        ;;
    esac
    case "$CONTAINER_EXIT_CODE" in
      ''|*[!0-9]*)
        echo "cpk-server liveness category=container-state-invalid" >&2
        return 1
        ;;
    esac
    case "$CONTAINER_OOM_KILLED" in
      true|false) ;;
      *)
        echo "cpk-server liveness category=container-state-invalid" >&2
        return 1
        ;;
    esac
    if [ "$CONTAINER_RUNNING" != "true" ]; then
      echo "cpk-server liveness category=container-exited running=$CONTAINER_RUNNING exit_code=$CONTAINER_EXIT_CODE oom_killed=$CONTAINER_OOM_KILLED" >&2
      return 1
    fi

    sleep 1
    attempt=$((attempt + 1))
  done

  HOST_CURL_ERROR_DETAIL="$(head -c "$HOST_CURL_ERROR_LIMIT" \
    "$HOST_CURL_ERROR" | tr '\r\n' '  ' | tr -cd '[:print:]')"
  if internal_liveness_probe; then
    echo "cpk-server liveness category=internal-live-host-unreachable running=$CONTAINER_RUNNING exit_code=$CONTAINER_EXIT_CODE oom_killed=$CONTAINER_OOM_KILLED host_curl_exit=$HOST_CURL_STATUS host_error=$HOST_CURL_ERROR_DETAIL" >&2
  else
    echo "cpk-server liveness category=internal-not-live running=$CONTAINER_RUNNING exit_code=$CONTAINER_EXIT_CODE oom_killed=$CONTAINER_OOM_KILLED host_curl_exit=$HOST_CURL_STATUS host_error=$HOST_CURL_ERROR_DETAIL" >&2
  fi
  return 1
}

invalid_published_port() {
    echo "cpk-server liveness category=invalid-published-port" >&2
    exit 1
}

trap finish EXIT
trap 'exit 130' INT TERM

phase "build product image"
if [ "$BUILD_IMAGE" = "1" ]; then
  docker build -f products/cpk_server/Dockerfile -t "$IMAGE" .
fi

phase "reject missing bootstrap configuration"
if docker run --rm "$IMAGE" >"$MISSING_CONFIG_OUTPUT" 2>&1; then
  echo "cpk-server started without required configuration" >&2
  exit 1
fi

phase "verify non-root image contract"
docker inspect "$IMAGE" --format '{{.Config.User}}' | grep -q '^10001$'

phase "create owned runtime network"
docker network create --label "$LABEL" "$NETWORK" >/dev/null

phase "start Postgres dependency"
POSTGRES_CONTAINER="$(docker run -d \
  --label "$LABEL" \
  --network "$NETWORK" \
  --network-alias cpk-postgres \
  -e POSTGRES_DB=cpk \
  -e POSTGRES_USER=cpk \
  -e POSTGRES_PASSWORD=cpk \
  postgres:16-alpine)"

phase "wait for Postgres semantic readiness"
POSTGRES_READY=0
for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if docker exec -e PGPASSWORD=cpk "$POSTGRES_CONTAINER" psql -h 127.0.0.1 -U cpk -d cpk -c 'SELECT 1' >/dev/null 2>&1; then
    POSTGRES_READY=1
    break
  fi
  sleep 1
done

if [ "$POSTGRES_READY" != "1" ]; then
  echo "postgres did not become query-ready" >&2
  exit 1
fi

# Generate after image/Postgres preparation so the240-second grants cover only
# startup and the immediate protected reads. No private key leaves the process.
if [ "$PROFILE" = "wrapped-source" ]; then
  phase "prepare synthetic source control authority"
  CONTROL_RECORDS="$(mktemp -d)"
  chmod 700 "$CONTROL_RECORDS"
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,source=$CONTROL_RECORDS,target=/fixture" \
    "$CPK_SERVERS_TEST_IMAGE" \
    python products/cpk_server/tests/source_control_fixture.py generate /fixture
fi

phase "start configured cpk-server"
set -- \
  -e CPK_SERVER_MODE=execution-capable \
  -e CPK_CONTROL_AUTH_VERIFIER=static-development \
  -e CPK_CONTROL_AUTH_STATIC_CREDENTIAL=valid-token \
  -e CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON="$STATIC_WORKSPACE_GRANTS_JSON" \
  -e CPK_PORT=8080 \
  -e CPK_RUNTIME_INTERPRETERS="$RUNTIME_INTERPRETERS" \
  -e CPK_WORKPLACE_DATABASE_URL="$WORKPLACE_DATABASE_URL" \
  -e CPK_ACTIVITY_HISTORY_DATABASE_URL="$ACTIVITY_HISTORY_DATABASE_URL" \
  -e CPK_OBSERVER_STATE_DATABASE_URL="$OBSERVER_STATE_DATABASE_URL" \
  -e CPK_GRAPH_TOPOLOGY_DATABASE_URL="$GRAPH_TOPOLOGY_DATABASE_URL"
if [ "$PROFILE" = "wrapped-source" ]; then
  phase "reject missing required source control file"
  if docker run --rm --network "$NETWORK" "$@" "$IMAGE" >"$MISSING_CONFIG_OUTPUT" 2>&1; then
    echo "cpk-server accepted missing control file" >&2
    exit 1
  fi
  grep -q 'CPK control configuration is invalid' "$MISSING_CONFIG_OUTPUT"
  set -- "$@" --mount "type=bind,source=$CONTROL_RECORDS/control.json,target=/etc/cpk/cpk-server/control.json,readonly"
fi
CONTAINER="$(docker run -d \
  --label "$LABEL" \
  --network "$NETWORK" \
  -p 127.0.0.1::8080 \
  "$@" "$IMAGE")"


PORT_BINDING="$(docker port "$CONTAINER" 8080/tcp)"
PORT_BINDING_LINES="$(printf '%s\n' "$PORT_BINDING" | wc -l | tr -d ' ')"
if [ "$PORT_BINDING_LINES" != "1" ]; then
  invalid_published_port
fi
case "$PORT_BINDING" in
  127.0.0.1:*) ;;
  *) invalid_published_port ;;
esac
PORT="${PORT_BINDING#127.0.0.1:}"
case "$PORT" in
  ''|*[!0-9]*) invalid_published_port ;;
esac
if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  invalid_published_port
fi
BASE="http://$REQUEST_HOST:$PORT"

phase "wait for cpk-server liveness"
if ! live="$(liveness_with_diagnostics "$BASE/health/live")"; then
  echo "cpk-server did not become live" >&2
  exit 1
fi

if [ "$PROFILE" = "wrapped-source" ]; then
  phase "verify authenticated source control health"
  (
    umask 077
    curl --connect-timeout 1 --max-time 3 --max-filesize 65536 --fail --silent --show-error \
      -H "@$CONTROL_RECORDS/surface.headers" \
      -o "$CONTROL_RECORDS/surface.json" "$BASE/__control/capabilities"
    curl --connect-timeout 1 --max-time 3 --max-filesize 65536 --fail --silent --show-error \
      -H "@$CONTROL_RECORDS/health.headers" \
      -o "$CONTROL_RECORDS/health.json" "$BASE/__control/health/liveness"
    for path in capabilities health/liveness; do
      denied="$(curl --connect-timeout 1 --max-time 3 --max-filesize 65536 --silent --show-error \
        -o "$CONTROL_RECORDS/denied.json" -w '%{http_code}' "$BASE/__control/$path")"
      [ "$denied" = "401" ]
    done
    denied="$(curl --connect-timeout 1 --max-time 3 --max-filesize 65536 --silent --show-error \
      -H "@$CONTROL_RECORDS/surface.headers" -o "$CONTROL_RECORDS/denied.json" \
      -w '%{http_code}' "$BASE/__control/health/liveness")"
    [ "$denied" = "401" ]
  )
  docker run --rm --network none --user "$(id -u):$(id -g)" \
    -e PYTHONDONTWRITEBYTECODE=1 \
    --mount "type=bind,source=$CONTROL_RECORDS,target=/fixture,readonly" \
    "$CPK_SERVERS_TEST_IMAGE" \
    python products/cpk_server/tests/source_control_fixture.py verify /fixture
  echo "cpk-server authenticated source control health passed"
fi

phase "verify cpk-server readiness"
printf '%s' "$live" | grep -q '"live"'
if ! ready="$(curl_with_retry "$BASE/health/ready")"; then
  echo "cpk-server did not become ready" >&2
  exit 1
fi
printf '%s' "$ready" | grep -q '"ready"'
printf '%s' "$ready" | grep -q '"stores"'
printf '%s' "$ready" | grep -q '"configured"'
if printf '%s' "$ready" | grep -q 'postgres://'; then
  echo "ready response leaked store endpoint" >&2
  exit 1
fi

phase "reject unauthenticated HTTP"
unauthorized_status="$(curl -sS -o "$UNAUTHORIZED_BODY" -w '%{http_code}' \
"$BASE/workspaces/workspace-a/graphs/current")"
[ "$unauthorized_status" = "401" ]

phase "reject unauthenticated MCP"
mcp_unauthorized_status="$(curl -sS -o "$MCP_UNAUTHORIZED_BODY" -w '%{http_code}' \
  -H 'Accept: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H 'Mcp-Method: tools/call' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"call-unauthorized","method":"tools/call","params":{"name":"command.deployment.plan","arguments":{"workspace_id":"workspace-a"}}}' \
"$BASE/mcp")"
[ "$mcp_unauthorized_status" = "401" ]

phase "authorize bounded missing-workspace read"
authorized_read="$(curl -sS \
  -H 'Authorization: Bearer valid-token' \
  "$BASE/workspaces/workspace-a")"
printf '%s' "$authorized_read" | grep -q 'missing workspace'
if printf '%s' "$authorized_read" | grep -q '"service"'; then
  echo "authorized read returned demo service echo" >&2
  exit 1
fi

phase "create workspace"
workspace_response="$(curl -fsS \
  -H 'Authorization: Bearer valid-token' \
  -H 'Content-Type: application/json' \
  -d '{"workspace_id":"workspace-a","name":"Workspace A","actor_id":"operator-a","idempotency_key":"workspace-a"}' \
  "$BASE/workspaces")"
printf '%s' "$workspace_response" | grep -q '"workspace_id":"workspace-a"'
printf '%s' "$workspace_response" | grep -q '"current_graph_id"'

phase "import product descriptor"
PRODUCT_DESCRIPTOR="$(cat products/hello_server/product.cpk.json)"
printf '{"descriptor_document":%s,"actor_id":"operator-a","imported_at":"2026-07-22T10:02:00Z","idempotency_key":"import-hello"}' \
  "$PRODUCT_DESCRIPTOR" >"$IMPORT_BODY"
product_response="$(curl -fsS \
  -H 'Authorization: Bearer valid-token' \
  -H 'Content-Type: application/json' \
  --data-binary "@$IMPORT_BODY" \
  "$BASE/workspaces/workspace-a/products/import")"
printf '%s' "$product_response" | grep -q '"name":"hello-server"'
printf '%s' "$product_response" | grep -q '"status":"active"'
rm -f "$IMPORT_BODY"

phase "start operation session"
session_response="$(curl -fsS \
  -H 'Authorization: Bearer valid-token' \
  -H 'Content-Type: application/json' \
  -d '{"actor_id":"operator-a","title":"Initial deployment","idempotency_key":"session-a"}' \
  "$BASE/workspaces/workspace-a/sessions")"
printf '%s' "$session_response" | grep -q '"session_id"'
SESSION_ID="$(printf '%s' "$session_response" | sed -n 's/.*"session_id":"\([^"]*\)".*/\1/p')"
if [ -z "$SESSION_ID" ]; then
  echo "session response did not contain parseable session_id" >&2
  exit 1
fi

phase "set desired graph"
desired_response="$(curl -fsS \
  -H 'Authorization: Bearer valid-token' \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"'"$SESSION_ID"'","actor_id":"operator-a","graph":{"name":"desired","runtimes":{},"nodes":{},"edges":{},"public_ingresses":[]},"expected_desired_graph_id":null,"idempotency_key":"desired-a"}' \
  "$BASE/workspaces/workspace-a/graphs/desired")"
printf '%s' "$desired_response" | grep -q '"desired_graph_id"'

phase "read workspace setup"
workspace_after_setup="$(curl -fsS \
  -H 'Authorization: Bearer valid-token' \
  "$BASE/workspaces/workspace-a")"
printf '%s' "$workspace_after_setup" | grep -q '"workspace_id":"workspace-a"'
printf '%s' "$workspace_after_setup" | grep -q '"desired_graph"'

phase "exercise authenticated MCP command"
mcp_response="$(curl -sS \
  -H 'Authorization: Bearer valid-token' \
  -H 'Accept: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H 'Mcp-Method: tools/call' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"call-1","method":"tools/call","params":{"name":"command.deployment.plan","arguments":{"workspace_id":"workspace-a"}}}' \
  "$BASE/mcp")"
printf '%s' "$mcp_response" | grep -q '"error"'
if printf '%s' "$mcp_response" | grep -q '"service"'; then
  echo "MCP command returned demo service echo" >&2
  exit 1
fi

phase "exercise authenticated MCP read"
mcp_read_response="$(curl -sS \
  -H 'Authorization: Bearer valid-token' \
  -H 'Accept: application/json' \
  -H 'MCP-Protocol-Version: 2025-06-18' \
  -H 'Mcp-Method: resources/read' \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":"read-1","method":"resources/read","params":{"name":"read.workspace","arguments":{"workspace_id":"workspace-a"}}}' \
  "$BASE/mcp")"
printf '%s' "$mcp_read_response" | grep -q '"workspace_id":"workspace-a"'
printf '%s' "$mcp_read_response" | grep -q '"desired_graph"'
if printf '%s' "$mcp_read_response" | grep -q '"service"'; then
  echo "MCP read returned demo service echo" >&2
  exit 1
fi

phase "verify packaged revision history HTTP and MCP composition"
# This is a public empty-history composition proof, not a second owner history
# fixture. All data enters through the already running authenticated server.
docker exec -i "$CONTAINER" python -I - "$SESSION_ID" <<'PY'
import json
import sys
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

base = "http://127.0.0.1:8080"

def request(path, payload=None, *, mcp=False, authenticated=True):
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["Authorization"] = "Bearer valid-token"
    if mcp:
        headers.update({"Accept": "application/json", "MCP-Protocol-Version": "2025-06-18",
                        "Mcp-Method": "resources/read"})
    call = Request(base + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        response = urlopen(call, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        data = response.read(65537)
        assert len(data) <= 65536, "empty-page smoke response exceeded its bounded expectation"
        return response.status, json.loads(data)

def mcp(name, arguments, **options):
    return request("/mcp", {"jsonrpc": "2.0", "id": "revision-history", "method": "resources/read",
        "params": {"name": name, "arguments": arguments}}, mcp=True, **options)

status, draft = request("/workspaces/workspace-a/desired-topology-drafts", {
    "session_id": sys.argv[1], "title": "Revision history smoke", "idempotency_key": "history-draft",
    "graph": {"name": "history-smoke", "runtimes": {}, "nodes": {}, "edges": {}, "public_ingresses": []}})
assert status == 200, (status, draft)
identity = {"workspace_id": "workspace-a", "draft_id": draft["draft_id"], "revision": draft["revision"]}
path = "/workspaces/workspace-a/desired-topology-drafts/" + quote(draft["draft_id"], safe="")
revision_path = path + "/revisions/" + str(draft["revision"])
for kind in ("preparations", "attempts"):
    route = "read.desired-topology-draft-revision-" + kind
    endpoint = revision_path + "/" + kind
    status, page = request(endpoint)
    assert status == 200, (status, page)
    assert page == {"workspace_id": "workspace-a", "kind": "desired-topology-draft-revision-" + kind,
                    "limit": 10, "items": [], "next_cursor": None}, page
    for name in (route, "list_desired_topology_draft_revision_" + kind):
        status, message = mcp(name, identity)
        assert status == 200 and message["result"] == page, (status, message)
    assert request(endpoint, authenticated=False)[0] == 401
    assert mcp(route, identity, authenticated=False)[0] == 401
    cursor = {"format_version": 1, "collection": "desired-topology-draft-revision-" + kind,
        "scope": {**identity, "draft_id": "other-draft"},
        "position": {"instant": "2026-09-07T00:00:00.000000Z", "item_id": "row-a"}}
    for query, arguments in (("limit=11", {**identity, "limit": 11}),
                            (urlencode({"after": json.dumps(cursor)}), {**identity, "after": cursor})):
        for status, error in (request(endpoint + "?" + query), mcp(route, arguments)):
            assert status == 400 and len(json.dumps(error).encode()) < 1024, (status, error)
    missing = {**identity, "revision": draft["revision"] + 1}
    missing_path = path + "/revisions/" + str(missing["revision"]) + "/" + kind
    for status, error in (request(missing_path), mcp(route, missing)):
        assert status == 404 and len(json.dumps(error).encode()) < 1024, (status, error)
status, detail = request(revision_path)
assert status == 200, (status, detail)
assert detail["history"] == {"scope": "source-or-target-sessions-and-exact-target-attempts",
    "preparations_present": False, "attempts_present": False, "completeness": "association-records-only"}
status, message = mcp("read.desired-topology-draft-revision", identity)
assert status == 200 and message["result"] == detail, (status, message)
print("packaged empty revision history HTTP/MCP composition passed")
PY

phase "clean owned smoke resources"
cleanup
cleanup_control_fixture
echo "cpk-server synthetic control fixture cleanup passed"
CONTAINER=""
POSTGRES_CONTAINER=""

phase "audit Docker residue"
sh scripts/docker_residue_audit.sh

phase "complete"
echo "cpk-server image smoke passed"
