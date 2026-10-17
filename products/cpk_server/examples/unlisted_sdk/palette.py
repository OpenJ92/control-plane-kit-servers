"""Independent JSON-configured palette, with default threaded host health."""
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
from control_plane_kit_server_sdk.stdlib import CpkThreadingHTTPServer


class Palette(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/palette":
            self.send_error(404)
            return
        body = self.server.palette_body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    with Path(os.environ["PALETTE_CONFIGURATION_FILE"]).open("rb") as configuration:
        raw = configuration.read(1025)
    if len(raw) > 1024:
        raise ValueError("palette configuration exceeds its bound")
    palette = json.loads(raw)
    if (type(palette) is not dict or set(palette) != {"colors"}
            or type(palette["colors"]) is not list or not 1 <= len(palette["colors"]) <= 8
            or any(type(color) is not str or not 1 <= len(color) <= 32 for color in palette["colors"])):
        raise ValueError("palette configuration is malformed")
    with CpkThreadingHTTPServer(("127.0.0.1", 0), Palette) as server:
        server.palette_body = json.dumps(palette, separators=(",", ":")).encode()
        print(server.server_port, flush=True)
        server.serve_forever(poll_interval=0.05)
