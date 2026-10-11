"""Independent SDK example: a static palette, with default threaded host health."""
from http.server import BaseHTTPRequestHandler
from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer


class Palette(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/palette":
            self.send_error(404)
            return
        body = b'{"colors":["indigo","amber"]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    with CpkThreadingHTTPServer(("127.0.0.1", 0), Palette) as server:
        print(server.server_port, flush=True)
        server.serve_forever(poll_interval=0.05)
