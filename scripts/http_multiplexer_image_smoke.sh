#!/bin/sh
set -eu

IMAGE="${HTTP_MULTIPLEXER_IMAGE:-cpk-http-multiplexer:local}"
CONTAINER="cpk-http-multiplexer-smoke"
PRIMARY="cpk-http-multiplexer-primary"
OBSERVER="cpk-http-multiplexer-observer"
NETWORK="cpk-http-multiplexer-smoke"
PORT="${HTTP_MULTIPLEXER_PORT:-18082}"
BUILD_IMAGE="${HTTP_MULTIPLEXER_BUILD_IMAGE:-1}"

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  docker rm -f "$PRIMARY" >/dev/null 2>&1 || true
  docker rm -f "$OBSERVER" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
}

trap cleanup EXIT
cleanup

if [ "$BUILD_IMAGE" = "1" ]; then
  docker build -f products/http_multiplexer/Dockerfile -t "$IMAGE" .
fi

docker network create \
  --label org.openj92.project=control-plane-kit-servers \
  "$NETWORK" >/dev/null

docker run -d \
  --name "$PRIMARY" \
  --network "$NETWORK" \
  --label org.openj92.project=control-plane-kit-servers \
  python:3.12-slim \
  python -c 'from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"primary response"
        self.send_response(200)
        self.send_header("content-type", "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        return
HTTPServer(("0.0.0.0", 8000), H).serve_forever()' >/dev/null

docker run -d \
  --name "$OBSERVER" \
  --network "$NETWORK" \
  --label org.openj92.project=control-plane-kit-servers \
  python:3.12-slim \
  python -c 'from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"observed"
        self.send_response(200)
        self.send_header("content-type", "text/plain")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args):
        print("observed " + self.path, flush=True)
HTTPServer(("0.0.0.0", 8000), H).serve_forever()' >/dev/null

docker run -d \
  --name "$CONTAINER" \
  --network "$NETWORK" \
  --label org.openj92.project=control-plane-kit-servers \
  -e MULTIPLEXER_PRIMARY_URL="http://$PRIMARY:8000" \
  -e MULTIPLEXER_OBSERVER_A_URL="http://$OBSERVER:8000" \
  -p "127.0.0.1:$PORT:8000" \
  "$IMAGE" >/dev/null

tries=0
until curl -fsS "http://127.0.0.1:$PORT/health/live" >/dev/null 2>&1; do
  tries=$((tries + 1))
  if [ "$tries" -gt 30 ]; then
    echo "multiplexer did not become live" >&2
    docker logs "$CONTAINER" >&2 || true
    exit 1
  fi
  sleep 1
done

BODY="$(curl -fsS "http://127.0.0.1:$PORT/anything")"
if [ "$BODY" != "primary response" ]; then
  echo "unexpected multiplexer response: $BODY" >&2
  exit 1
fi

tries=0
until docker logs "$OBSERVER" 2>/dev/null | grep -q "observed /anything"; do
  tries=$((tries + 1))
  if [ "$tries" -gt 30 ]; then
    echo "observer did not receive copied request" >&2
    docker logs "$OBSERVER" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "http-multiplexer image smoke passed: $BODY and observer received copy"
