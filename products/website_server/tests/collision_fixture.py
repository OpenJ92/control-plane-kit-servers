"""Test-only foreign visitor listener with identical selected index bytes."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from control_plane_kit_servers_website_server.process import main

content = Path("/app/dist/index.html").read_bytes()


class ForeignHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_args):
        return


foreign = ThreadingHTTPServer(("0.0.0.0",8080), ForeignHandler)
foreign.daemon_threads = True
Thread(target=foreign.serve_forever,daemon=True).start()
raise SystemExit(main())
