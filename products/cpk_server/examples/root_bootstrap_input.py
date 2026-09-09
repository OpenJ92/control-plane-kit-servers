"""Print a portable input using this checkout's accepted descriptor documents.

Run in the bootstrap driver with the checkout mounted at /source. This creates
no credentials, plans, registrations or resources. Edit the printed values and
explicit grants before reviewing a plan.
"""

import json
from pathlib import Path


def example_input(source=Path("/source"), *, installation_id="root-a", workspace_id="root-workspace", port=18080):
    def product(directory, filename="product.cpk.json"):
        return json.loads((source / "products" / directory / filename).read_text())

    return {
        "schema": "cpk.root-bootstrap.input.v1",
        "installation": {
            "installation_id": installation_id, "workspace_id": workspace_id,
            "runtime_authority": "external-root-docker",
            "runtime_access": {"authority_ref": {"reference_id": "root-docker-access"},
                "delivery_kind": "local-docker-socket-mount", "secret_references": []},
            "products": {"cpk": product("cpk_server", "product.docker-cloudflare.cpk.json"),
                         "postgres": product("postgres_server"), "secrets": product("secrets_server")},
            "references": {
                "control_credential": f"secret://bootstrap/{installation_id}/control",
                "postgres_password": f"secret://bootstrap/{installation_id}/postgres",
                "custody_root_key": f"secret://bootstrap/{installation_id}/custody",
                "provider_credentials_document": f"secret://bootstrap/{installation_id}/grants",
                "provider_client_credential": f"secret://bootstrap/{installation_id}/client",
                "provider_bootstrap_credential_ref": "secret://control-plane-kit/bootstrap/client",
            },
            "workspace_grants": [{"workspace_id": workspace_id, "scopes": [
                "hub:instance:create", "instance:workspace:read", "instance:workspace:edit",
                "runtime-authority:register", "runtime-authority:read",
                "runtime-authority-delivery:register", "runtime-authority-delivery:read",
                "secret-provider:register", "secret-provider:read",
            ]}],
            "provider_endpoint_ref": "root-provider", "external_endpoint": "https://root.example.test",
        },
        "host_binding": {"address": "127.0.0.1", "port": port},
        "setup": {"workspace_name": "Root workspace",
            "provider": {"provider_id": "control-plane-kit",
                "allowed_reference_prefixes": [f"secret://control-plane-kit/{workspace_id}"],
                "allowed_intents": ["postgres.password", "application.control-token"]},
            "secret_references": [], "image_pull_authorities": [], "ingress_authorities": []},
    }


if __name__ == "__main__":
    print(json.dumps(example_input(), indent=2))
