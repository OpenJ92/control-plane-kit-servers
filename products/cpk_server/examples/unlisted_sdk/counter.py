"""Independent SDK example: an ordinary request counter, with default host health."""
from http.server import BaseHTTPRequestHandler
from control_plane_kit_server_sdk.stdlib import CpkHTTPServer


class Counter(BaseHTTPRequestHandler):
    count = 0

    def do_GET(self):
        if self.path != "/count":
            self.send_error(404)
            return
        type(self).count += 1
        body = str(type(self).count).encode("ascii")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    # SDK reads CPK_WRAPPER_CONFIGURATION_FILE; no identity/trust or health callback.
    with CpkHTTPServer(("127.0.0.1", 0), Counter) as server:
        print(server.server_port, flush=True)
        server.serve_forever(poll_interval=0.05)
