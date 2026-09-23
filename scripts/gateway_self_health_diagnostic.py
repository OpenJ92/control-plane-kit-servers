"""Container entrypoint for the explicitly approved operator diagnostic."""
from control_plane_kit_servers_cpk_server.gateway_self_health_diagnostic import main

if __name__ == "__main__":
    raise SystemExit(main())
