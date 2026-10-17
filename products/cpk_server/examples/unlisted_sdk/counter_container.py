"""Private container host for the independent counter; health belongs to SDK."""
from counter import Counter
from control_plane_kit_server_sdk.stdlib import CpkHTTPServer


if __name__ == "__main__":
    with CpkHTTPServer(("0.0.0.0", 8000), Counter) as server:
        server.serve_forever(poll_interval=0.05)
