from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from control_plane_kit_core.delegation_authority import (
    DelegationVerifierProjection,
    materialize_delegation_verifiers,
)
from control_plane_kit_core.delegation_keys import (
    DelegationKeyAlgorithm,
    DelegationKeyPurpose,
    DelegationPublicKey,
)
from control_plane_kit_core.gateway_delegation import GatewayProbeAccessPath
from control_plane_kit_core.topology import DEFAULT_GRAPH_CODEC


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cpk_server_hosted_activity as hosted  # noqa: E402


def _load_source_live_module():
    spec = importlib.util.spec_from_file_location(
        "cpk_server_secret_provider_source_live_access_paths",
        SCRIPTS / "cpk_server_secret_provider_source_live.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("source-live controller module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _public_key(key_id: str) -> DelegationPublicKey:
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return DelegationPublicKey(
        key_id=key_id,
        algorithm=DelegationKeyAlgorithm.ED25519,
        public_key_pem=public_pem,
    )


class GatewayRotationAccessPathTests(unittest.TestCase):
    def test_rotation_advance_uses_bounded_effect_transport_timeout(self) -> None:
        workflow = hosted.HostedWorkflow(
            "http://cpk-server:8080",
            workspace_id="workspace-a",
            worker_id="worker-a",
            server_container="cpk-server",
        )
        with (
            patch.object(hosted, "_http", return_value={}) as http,
            patch.object(hosted, "_mcp_tool", return_value={}) as mcp,
        ):
            workflow.advance_gateway_key_rotation_http(
                rotation_id="rotation-a",
                expected_version=4,
                idempotency_key="advance-http",
            )
            workflow.advance_gateway_key_rotation_mcp(
                rotation_id="rotation-a",
                expected_version=5,
                idempotency_key="advance-mcp",
            )

        self.assertEqual(http.call_args.kwargs["timeout"], 60)
        self.assertEqual(mcp.call_args.kwargs["timeout"], 60)

    def test_hosted_workflow_forwards_closed_access_path_over_http_and_mcp(self) -> None:
        workflow = hosted.HostedWorkflow(
            "http://cpk-server:8080",
            workspace_id="workspace-a",
            worker_id="worker-a",
            server_container="cpk-server",
        )
        observed: list[tuple[str, dict[str, object]]] = []

        def capture_http(_base_url, _method, _path, payload, **_kwargs):
            observed.append(("http", payload))
            return {"gateway_probe": {"access_path": payload["access_path"]}}

        def capture_mcp(_base_url, _tool, payload):
            observed.append(("mcp", payload))
            return {"gateway_probe": {"access_path": payload["access_path"]}}

        with (
            patch.object(hosted, "_http", side_effect=capture_http),
            patch.object(hosted, "_mcp_tool", side_effect=capture_mcp),
        ):
            http_result = workflow.request_gateway_probe_http(
                request_id="probe-http",
                expected_current_graph_id="graph-current",
                gateway_node_id="gateway",
                kind="http-status",
                target_id="hello.internal",
                path="/",
                access_path=GatewayProbeAccessPath.NAMED_PUBLIC_INGRESS,
            )
            mcp_result = workflow.request_gateway_probe_mcp(
                request_id="probe-mcp",
                expected_current_graph_id="graph-current",
                gateway_node_id="gateway",
                kind="postgres-select-one",
                target_id="postgres.postgres",
                access_path=GatewayProbeAccessPath.RUNTIME_PRIVATE,
            )

        self.assertEqual(
            observed[0][1]["access_path"],
            GatewayProbeAccessPath.NAMED_PUBLIC_INGRESS.value,
        )
        self.assertEqual(
            observed[1][1]["access_path"],
            GatewayProbeAccessPath.RUNTIME_PRIVATE.value,
        )
        self.assertEqual(
            http_result["gateway_probe"]["access_path"],
            GatewayProbeAccessPath.NAMED_PUBLIC_INGRESS.value,
        )
        self.assertEqual(
            mcp_result["gateway_probe"]["access_path"],
            GatewayProbeAccessPath.RUNTIME_PRIVATE.value,
        )

    def test_rotation_public_graph_preserves_overlay_across_a_ab_b(self) -> None:
        module = _load_source_live_module()
        graph = module._gateway_rotation_public_graph(
            module._product_document(ROOT, "cpk_local_gateway"),
            module._product_document(ROOT, "hello_server"),
            module._product_document(ROOT, "postgres_server"),
            module._product_document(ROOT, "cloudflared_connector"),
            workspace_id="workspace-rotation-public",
            public_hostname="cpk-rotation-public.openj92.dev",
        )

        self.assertEqual(
            set(graph.nodes),
            {"gateway", "hello", "postgres", "cloudflared-gateway"},
        )
        self.assertEqual(len(graph.edges), 2)
        self.assertEqual(len(graph.public_ingresses), 1)
        self.assertEqual(
            {
                check.check_id
                for check in graph.nodes["gateway"].block_spec.verification.checks
            },
            {"live", "ready"},
        )
        ingress = graph.public_ingresses[0]
        self.assertEqual(ingress.target.node_id, "gateway")
        self.assertEqual(ingress.target.provider_socket, "control")
        self.assertEqual(ingress.connector_node_id, "cloudflared-gateway")
        self.assertEqual(ingress.hostname, "cpk-rotation-public.openj92.dev")

        key_a = _public_key("key-a")
        key_b = _public_key("key-b")
        projections = (
            ("projection-a", (key_a,)),
            ("projection-a-b", (key_a, key_b)),
            ("projection-b", (key_b,)),
        )
        authored = DEFAULT_GRAPH_CODEC.encode(graph)
        authored_text = json.dumps(authored, sort_keys=True)
        self.assertNotIn("BEGIN PRIVATE KEY", authored_text)
        self.assertNotIn("cloudflare-api-token-value", authored_text)
        for projection_id, keys in projections:
            with self.subTest(projection_id=projection_id):
                projected = materialize_delegation_verifiers(
                    graph,
                    (
                        DelegationVerifierProjection(
                            delegate_node_id="gateway",
                            purpose=DelegationKeyPurpose.GATEWAY_PROBE,
                            issuer=module.GATEWAY_ROTATION_ISSUER,
                            audience="gateway:workspace-rotation-public:gateway",
                            projection_id=projection_id,
                            public_keys=keys,
                        ),
                    ),
                )
                descriptor = DEFAULT_GRAPH_CODEC.encode(projected)
                self.assertEqual(
                    descriptor["public_ingresses"], authored["public_ingresses"]
                )
                self.assertEqual(descriptor["edges"], authored["edges"])
                self.assertEqual(descriptor["runtimes"], authored["runtimes"])
                self.assertEqual(
                    descriptor["delegation_authorities"],
                    authored["delegation_authorities"],
                )
                for node_id in ("hello", "postgres", "cloudflared-gateway"):
                    self.assertEqual(
                        descriptor["nodes"][node_id],
                        authored["nodes"][node_id],
                    )


if __name__ == "__main__":
    unittest.main()
