"""Production modules required by the installer, shared by source/artifact proof."""
REQUIRED_IMPORTS = (
    "control_plane_kit_servers_cpk_server.bootstrap_cli",
    "control_plane_kit_servers_cpk_server.bootstrap",
    "control_plane_kit_servers_cpk_server.root_material_preparation",
    "control_plane_kit_secrets.control",
    "control_plane_kit_secrets.bootstrap",
    "control_plane_kit_servers_website_server.managed",
    "control_plane_kit_servers_postgres_server.configuration",
)
RUNTIME_DEPENDENCIES = ("docker", "requests", "httpx", "psycopg", "cryptography")
