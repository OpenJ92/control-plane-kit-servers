#!/bin/sh
set -eu

IMAGE="${HTTP_ACTIVE_ROUTER_IMAGE:-cpk-http-active-router:local}"
CONTAINER="cpk-http-active-router-smoke"
UPSTREAM="cpk-http-active-router-upstream"
NETWORK="cpk-http-active-router-smoke"
PORT="${HTTP_ACTIVE_ROUTER_PORT:-18081}"
BUILD_IMAGE="${HTTP_ACTIVE_ROUTER_BUILD_IMAGE:-1}"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker rm -f "$UPSTREAM" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}

trap cleanup EXIT
cleanup

if [ "$BUILD_IMAGE" = "1" ]; then
  docker build -f products/http_active_router/Dockerfile -t "$IMAGE" .
fi

docker network create \
  --label org.openj92.project=control-plane-kit-servers \
  "$NETWORK" >/dev/null

docker run -d \
  --name "$UPSTREAM" \
  --network "$NETWORK" \
  --label org.openj92.project=control-plane-kit-servers \
  python:3.12-slim \
  python -c 'from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"active upstream"
        self.send_response(200)
        self.send_header("content-type", "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        return
HTTPServer(("0.0.0.0", 8000), H).serve_forever()' >/dev/null

docker run -d \
  --name "$CONTAINER" \
  --network "$NETWORK" \
  --label org.openj92.project=control-plane-kit-servers \
  -e ACTIVE_TARGET_URL="http://$UPSTREAM:8000" \
  -p "127.0.0.1:$PORT:8000" \
  "$IMAGE" >/dev/null

tries=0
until curl -fsS "http://127.0.0.1:$PORT/health/live" >/dev/null; do
  tries=$((tries + 1))
  if [ "$tries" -gt 30 ]; then
    echo "router did not become live" >&2
    docker logs "$CONTAINER" >&2 || true
    exit 1
  fi
  sleep 1
done

BODY="$(curl -fsS "http://127.0.0.1:$PORT/anything")"
if [ "$BODY" != "active upstream" ]; then
  echo "unexpected router response: $BODY" >&2
  exit 1
fi

echo "http-active-router image smoke passed: $BODY"
