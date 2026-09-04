from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from control_plane_kit_core.gateway_delegation import GatewayProbeAccessPath


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cpk_server_hosted_activity as hosted  # noqa: E402


class GatewayRotationAccessPathTests(unittest.TestCase):
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

if __name__ == "__main__":
    unittest.main()
