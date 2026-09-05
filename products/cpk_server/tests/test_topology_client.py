import contextlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest.mock import patch
from uuid import UUID


ROOT = Path(__file__).resolve().parents[3]
PRODUCT_SRC = ROOT / "products" / "cpk_server" / "src"


class ScriptedTransport:
    def __init__(
        self,
        *,
        lose_prepare_once: bool = False,
        destructive: bool = False,
        progress_once: bool = False,
        attention_status: str | None = None,
    ) -> None:
        self.calls = []
        self.lose_prepare_once = lose_prepare_once
        self.destructive = destructive
        self.progress_once = progress_once
        self.attention_status = attention_status
        self.approved = False
        self.advanced = False

    def call(self, route_id, *, path_parameters, payload, credential_role):
        record = {
            "route_id": route_id,
            "path_parameters": dict(path_parameters),
            "payload": dict(payload),
            "credential_role": credential_role,
        }
        self.calls.append(record)
        if route_id == "read.workspace":
            return {
                "workspace": {
                    "workspace_id": "workspace-a",
                    "current_graph_id": "graph-desired" if self.advanced else "graph-current",
                    "current_realized_projection_id": (
                        "projection-desired" if self.advanced else "projection-current"
                    ),
                    "desired_graph_id": None,
                    "desired_realized_projection_id": None,
                    "desired_graph_revision": 0,
                }
            }
        if route_id == "command.deployment.prepare":
            if self.lose_prepare_once:
                self.lose_prepare_once = False
                from control_plane_kit_servers_cpk_server.client import ClientTransportError

                raise ClientTransportError()
            return {
                "status": "approval-required",
                "workspace_id": "workspace-a",
                "plan_id": "plan-a",
                "approval_request_id": "approval-a",
            }
        if route_id == "read.plan-detail":
            return {
                "plan": {
                    "plan_id": "plan-a",
                    "session_id": "session-a",
                    "base_graph_id": "graph-current",
                    "base_realized_projection_id": "projection-current",
                    "desired_graph_id": "graph-desired",
                    "desired_realized_projection_id": "projection-desired",
                    "desired_graph_revision": 1,
                    "payload": {
                        "activities": [
                            {
                                "activity_id": "activity-a",
                                "operation": {
                                    "kind": (
                                        "delete-node"
                                        if self.destructive
                                        else "create-node"
                                    ),
                                    "target": {
                                        "kind": "node",
                                        "node_id": "hello-a",
                                    },
                                },
                            }
                        ]
                    },
                }
            }
        if route_id == "read.approval-detail":
            return {
                "approval": {
                    "request_id": "approval-a",
                    "session_id": "session-a",
                    "required_scope": (
                        "plan:approve-destructive" if self.destructive else "plan:approve"
                    ),
                    "destructive": self.destructive,
                    "state": "approved" if self.approved else "pending",
                }
            }
        if route_id == "command.approval.decide":
            self.approved = True
            return {"state": "approved", "request_id": "approval-a", "replayed": False}
        if route_id == "command.deployment.admit":
            return {"execution_request_id": "request-a", "replayed": False}
        if route_id == "command.run.claim":
            return {
                "execution_request_id": "request-a",
                "run_id": "run-a",
                "run_status": "claimed",
                "claim_generation": 1,
                "replayed": False,
            }
        if route_id == "command.run.start":
            return {
                "execution_request_id": "request-a",
                "run_id": "run-a",
                "run_status": "running",
                "claim_generation": 1,
                "replayed": False,
            }
        if route_id == "command.deployment.execute":
            if self.attention_status is not None:
                return {
                    "run_id": "run-a",
                    "run_status": "running",
                    "coordinator_status": self.attention_status,
                    "effects_attempted": 1,
                    "activity_id": "activity-a",
                }
            if self.progress_once:
                self.progress_once = False
                return {
                    "run_id": "run-a",
                    "run_status": "running",
                    "coordinator_status": "progressed",
                    "effects_attempted": 1,
                    "activity_id": "activity-a",
                }
            return {
                "run_id": "run-a",
                "run_status": "succeeded",
                "coordinator_status": "completed",
                "effects_attempted": 1,
                "activity_id": None,
            }
        if route_id == "command.graph.advance-current":
            self.advanced = True
            return {
                "from_graph_id": "graph-current",
                "to_graph_id": "graph-desired",
                "from_realized_projection_id": "projection-current",
                "to_realized_projection_id": "projection-desired",
                "desired_graph_revision": 1,
                "replayed": False,
            }
        if route_id == "read.current-graph":
            return {
                "graph_id": "graph-desired" if self.advanced else "graph-current",
                "realized_projection_id": (
                    "projection-desired" if self.advanced else "projection-current"
                ),
            }
        if route_id == "read.plan-runs":
            return {
                "items": [
                    {
                        "run_id": "run-a",
                        "status": "succeeded" if self.advanced else "running",
                    }
                ],
                "next_cursor": None,
            }
        if route_id == "read.run-events":
            return {"items": [], "next_cursor": None}
        raise AssertionError(f"unexpected route: {route_id}")


class LostWorkspaceAfterExecuteTransport(ScriptedTransport):
    def __init__(self) -> None:
        super().__init__()
        self.executed = False
        self.lost = False

    def call(self, route_id, *, path_parameters, payload, credential_role):
        if route_id == "read.workspace" and self.executed and not self.lost:
            self.lost = True
            self.calls.append(
                {
                    "route_id": route_id,
                    "path_parameters": dict(path_parameters),
                    "payload": dict(payload),
                    "credential_role": credential_role,
                }
            )
            from control_plane_kit_servers_cpk_server.client import ClientTransportError

            raise ClientTransportError()
        result = super().call(
            route_id,
            path_parameters=path_parameters,
            payload=payload,
            credential_role=credential_role,
        )
        if (
            route_id == "command.deployment.execute"
            and result.get("coordinator_status") == "completed"
        ):
            self.executed = True
        return result


class LostCurrentAfterAdvanceTransport(ScriptedTransport):
    def __init__(self) -> None:
        super().__init__()
        self.lost = False

    def call(self, route_id, *, path_parameters, payload, credential_role):
        if route_id == "read.current-graph" and self.advanced and not self.lost:
            self.lost = True
            self.calls.append(
                {
                    "route_id": route_id,
                    "path_parameters": dict(path_parameters),
                    "payload": dict(payload),
                    "credential_role": credential_role,
                }
            )
            from control_plane_kit_servers_cpk_server.client import ClientTransportError

            raise ClientTransportError()
        return super().call(
            route_id,
            path_parameters=path_parameters,
            payload=payload,
            credential_role=credential_role,
        )


class DeterministicIds:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return str(UUID(int=self.value, version=4))


class TopologyClientTests(unittest.TestCase):
    def setUp(self) -> None:
        sys.path.insert(0, str(PRODUCT_SRC))
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.desired_path = self.root / "desired.json"
        self.desired = {
            "workspace_id": "workspace-a",
            "nodes": {
                "hello-a": {
                    "configuration": {"message": "Hello"},
                    "secret_deliveries": [
                        {"reference": "secret://hello/token", "target": "TOKEN"}
                    ],
                }
            },
            "edges": [],
        }
        self.desired_path.write_text(json.dumps(self.desired), encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()
        sys.path.remove(str(PRODUCT_SRC))
        for name in list(sys.modules):
            if name == "control_plane_kit_servers_cpk_server" or name.startswith(
                "control_plane_kit_servers_cpk_server."
            ):
                sys.modules.pop(name, None)

    def profile(
        self,
        *,
        endpoint: str = "https://cpk.example",
        workspace: str = "workspace-a",
        state: str = "state",
    ):
        from control_plane_kit_servers_cpk_server.client import ClientProfile

        credentials = {
            role: self.root / f"{role}.token"
            for role in ("operator", "approver", "worker")
        }
        return ClientProfile(endpoint, workspace, credentials, self.root / state)

    def client(self, transport, *, state: str = "state"):
        from control_plane_kit_servers_cpk_server.client import TopologyClient

        return TopologyClient(
            self.profile(state=state),
            transport=transport,
            identity_factory=DeterministicIds(),
        )

    def test_public_chain_uses_each_route_coordinate_and_own_replay_contract(self) -> None:
        transport = ScriptedTransport(progress_once=True)
        client = self.client(transport)

        planned = client.plan(self.desired_path, title="Any supported graph")
        before_apply = tuple(transport.calls)
        completed = client.apply(
            planned.operation_ref,
            execute_plan=planned.plan_id,
            approve_plan=planned.plan_id,
        )

        self.assertEqual(planned.status, "planned")
        self.assertEqual(planned.changes[0]["operation"], "create-node")
        self.assertEqual(
            planned.changes[0]["target"],
            {"kind": "node", "node_id": "hello-a"},
        )
        self.assertFalse(
            any(
                call["route_id"].startswith("command.")
                and call["route_id"] != "command.deployment.prepare"
                for call in before_apply
            )
        )
        self.assertEqual(completed.status, "converged")
        self.assertEqual(completed.execution, "succeeded")
        self.assertEqual(completed.advancement, "advanced")
        prepare = next(
            call for call in transport.calls
            if call["route_id"] == "command.deployment.prepare"
        )
        self.assertEqual(prepare["payload"]["desired_graph"], self.desired)
        claim = next(
            call for call in transport.calls if call["route_id"] == "command.run.claim"
        )
        self.assertEqual(claim["path_parameters"]["run_id"], "request-a")
        self.assertEqual(claim["credential_role"], "worker")
        roles = {
            "command.approval.decide": "approver",
            "command.deployment.admit": "operator",
            "command.run.claim": "worker",
            "command.run.start": "worker",
            "command.deployment.execute": "worker",
            "command.graph.advance-current": "worker",
        }
        for route_id, role in roles.items():
            expected = 2 if route_id == "command.deployment.execute" else 1
            calls = [call for call in transport.calls if call["route_id"] == route_id]
            self.assertEqual(len(calls), expected, route_id)
            self.assertTrue(all(call["credential_role"] == role for call in calls))
            self.assertTrue(all("idempotency_key" in call["payload"] for call in calls))
        execute_keys = [
            call["payload"]["idempotency_key"]
            for call in transport.calls
            if call["route_id"] == "command.deployment.execute"
        ]
        self.assertEqual(len(execute_keys), len(set(execute_keys)))

        destructive_transport = ScriptedTransport(destructive=True)
        destructive_client = self.client(destructive_transport, state="destructive-state")
        destructive_plan = destructive_client.plan(self.desired_path)
        from control_plane_kit_servers_cpk_server.client import (
            ClientInputError,
            ClientTransportError,
        )

        for arguments in (
            {"execute_plan": "plan-b"},
            {"execute_plan": "plan-a", "approve_plan": "plan-a"},
        ):
            with self.subTest(arguments=arguments), self.assertRaises(ClientInputError):
                destructive_client.apply(destructive_plan.operation_ref, **arguments)
        self.assertFalse(
            any(
                call["route_id"] == "command.approval.decide"
                for call in destructive_transport.calls
            )
        )
        self.assertEqual(destructive_plan.changes[0]["operation"], "delete-node")

        class LostApprovalTransport(ScriptedTransport):
            def __init__(self) -> None:
                super().__init__()
                self.lost = False

            def call(self, route_id, *, path_parameters, payload, credential_role):
                if route_id == "command.approval.decide" and not self.lost:
                    self.lost = True
                    self.calls.append(
                        {
                            "route_id": route_id,
                            "path_parameters": dict(path_parameters),
                            "payload": dict(payload),
                            "credential_role": credential_role,
                        }
                    )
                    raise ClientTransportError()
                return super().call(
                    route_id,
                    path_parameters=path_parameters,
                    payload=payload,
                    credential_role=credential_role,
                )

        pending_transport = LostApprovalTransport()
        pending_client = self.client(pending_transport, state="pending-state")
        pending_plan = pending_client.plan(self.desired_path)
        unresolved = pending_client.apply(
            pending_plan.operation_ref,
            execute_plan="plan-a",
            approve_plan="plan-a",
        )
        calls_before_wrong_plan = tuple(pending_transport.calls)
        with self.assertRaises(ClientInputError):
            pending_client.apply(
                pending_plan.operation_ref,
                execute_plan="plan-b",
                approve_plan="plan-b",
            )
        self.assertEqual(unresolved.status, "attention-required")
        self.assertEqual(tuple(pending_transport.calls), calls_before_wrong_plan)

    def _assert_profile_and_cli_contract(self) -> None:
        from control_plane_kit_servers_cpk_server.client import (
            ClientConfigurationError,
            ClientProfile,
            ClientResult,
            load_profile,
        )
        from control_plane_kit_servers_cpk_server.client import cli

        profile_root = self.root / "cpk" / "profiles"
        profile_root.mkdir(parents=True)
        credentials = {}
        for role in ("operator", "approver", "worker"):
            path = self.root / f"{role}.token"
            path.write_text(f"{role}-token", encoding="ascii")
            path.chmod(0o600)
            credentials[role] = str(path)
        profile_path = profile_root / "local.json"
        profile_path.write_text(
            json.dumps(
                {
                    "schema": "cpk.client-profile.v1",
                    "endpoint": "http://127.0.0.1:8080",
                    "workspace_id": "workspace-a",
                    "credentials": credentials,
                    "state_directory": str(self.root / "profile-state"),
                }
            ),
            encoding="utf-8",
        )
        profile_path.chmod(0o600)
        profile = load_profile("local", config_home=self.root)
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        result = ClientResult(
            "attention-required",
            "00000000-0000-4000-8000-000000000001",
            "workspace-a",
            execution="unverified",
            advancement="unverified",
            next_public_read="read.workspace",
        )

        class StubClient:
            def __init__(self, _profile: ClientProfile) -> None:
                pass

            def status(self, _operation_ref: str) -> ClientResult:
                return result

        output = io.StringIO()
        with patch.object(cli, "load_profile", return_value=profile), patch.object(
            cli, "TopologyClient", StubClient
        ), contextlib.redirect_stdout(output):
            exit_code = cli.main(
                [
                    "--profile",
                    "local",
                    "status",
                    result.operation_ref,
                    "--json",
                ]
            )

        self.assertEqual(exit_code, 4)
        self.assertEqual(json.loads(output.getvalue()), result.descriptor())
        self.assertEqual(
            metadata["project"]["scripts"]["cpk"],
            "control_plane_kit_servers_cpk_server.client.cli:main",
        )
        with self.assertRaises(ClientConfigurationError):
            load_profile("../local", config_home=self.root)
        symlink = profile_root / "linked.json"
        symlink.symlink_to(profile_path)
        with self.assertRaises(ClientConfigurationError):
            load_profile("linked", config_home=self.root)

    def test_lost_prepare_replays_exact_request_or_returns_attention_without_mutation(
        self,
    ) -> None:
        transport = ScriptedTransport(lose_prepare_once=True)
        client = self.client(transport)

        unresolved = client.plan(self.desired_path)
        calls_before_status = len(transport.calls)
        observed = client.status(unresolved.operation_ref)
        resumed = client.resume_prepare(unresolved.operation_ref)

        self.assertEqual(unresolved.status, "attention-required")
        self.assertEqual(unresolved.exit_code, 4)
        self.assertEqual(observed.status, "attention-required")
        self.assertEqual(len(transport.calls), calls_before_status + 4)
        prepare_calls = [
            call for call in transport.calls
            if call["route_id"] == "command.deployment.prepare"
        ]
        self.assertEqual(len(prepare_calls), 2)
        self.assertEqual(prepare_calls[0], prepare_calls[1])
        self.assertEqual(resumed.status, "planned")

        class LostPlanReadTransport(ScriptedTransport):
            def __init__(self) -> None:
                super().__init__()
                self.lost = False

            def call(self, route_id, *, path_parameters, payload, credential_role):
                if route_id == "read.plan-detail" and not self.lost:
                    self.lost = True
                    self.calls.append(
                        {
                            "route_id": route_id,
                            "path_parameters": dict(path_parameters),
                            "payload": dict(payload),
                            "credential_role": credential_role,
                        }
                    )
                    from control_plane_kit_servers_cpk_server.client import (
                        ClientTransportError,
                    )

                    raise ClientTransportError()
                return super().call(
                    route_id,
                    path_parameters=path_parameters,
                    payload=payload,
                    credential_role=credential_role,
                )

        lost_read_transport = LostPlanReadTransport()
        lost_read_client = self.client(lost_read_transport, state="lost-plan-state")
        lost_read = lost_read_client.plan(self.desired_path)
        self.assertEqual(lost_read.status, "attention-required")
        self.assertEqual(lost_read.next_public_read, "read.plan-detail")
        self.assertTrue(lost_read.operation_ref)
        self.assertEqual(
            [
                call["route_id"]
                for call in lost_read_transport.calls
                if call["route_id"].startswith("command.")
            ],
            ["command.deployment.prepare"],
        )

    def test_unresolved_dispatch_is_unverified_attention_with_nonzero_exit(self) -> None:
        from control_plane_kit_servers_cpk_server.client import ClientTransportError

        class LostExecuteTransport(ScriptedTransport):
            def __init__(self) -> None:
                super().__init__()
                self.lost = False

            def call(self, route_id, **arguments):
                if route_id == "command.deployment.execute" and not self.lost:
                    self.lost = True
                    self.calls.append({"route_id": route_id, **arguments})
                    raise ClientTransportError()
                return super().call(route_id, **arguments)

        transport = LostExecuteTransport()
        client = self.client(transport)
        planned = client.plan(self.desired_path)

        result = client.apply(
            planned.operation_ref,
            execute_plan="plan-a",
            approve_plan="plan-a",
        )

        self.assertEqual(result.status, "attention-required")
        self.assertEqual(result.execution, "unverified")
        self.assertEqual(result.advancement, "not-attempted")
        self.assertEqual(result.next_public_read, "read.run-events")
        self.assertEqual(result.exit_code, 4)
        self.assertFalse(
            any(
                call["route_id"] == "command.graph.advance-current"
                for call in transport.calls
            )
        )
        calls_before_resume = len(transport.calls)
        resumed = client.apply(
            planned.operation_ref,
            execute_plan="plan-a",
        )
        resumed_calls = transport.calls[calls_before_resume:]
        replay_index = next(
            index
            for index, call in enumerate(resumed_calls)
            if call["route_id"] == "command.deployment.execute"
        )
        self.assertEqual(resumed.status, "converged")
        self.assertTrue(
            any(
                call["route_id"] == "read.plan-runs"
                for call in resumed_calls[:replay_index]
            )
        )
        self.assertTrue(
            any(
                call["route_id"] == "read.run-events"
                for call in resumed_calls[:replay_index]
            )
        )

        in_flight_transport = ScriptedTransport(attention_status="in-flight")
        in_flight_client = self.client(in_flight_transport, state="in-flight-state")
        in_flight_plan = in_flight_client.plan(self.desired_path)
        in_flight = in_flight_client.apply(
            in_flight_plan.operation_ref,
            execute_plan="plan-a",
            approve_plan="plan-a",
        )
        self.assertEqual(in_flight.status, "attention-required")
        self.assertEqual(in_flight.execution, "running")
        self.assertNotEqual(in_flight.execution, "in-flight")

        for name, transport_type in (
            ("workspace-after-execute", LostWorkspaceAfterExecuteTransport),
            ("current-after-advance", LostCurrentAfterAdvanceTransport),
        ):
            with self.subTest(readback=name):
                readback_transport = transport_type()
                readback_client = self.client(
                    readback_transport,
                    state=f"{name}-state",
                )
                readback_plan = readback_client.plan(self.desired_path)
                readback = readback_client.apply(
                    readback_plan.operation_ref,
                    execute_plan="plan-a",
                    approve_plan="plan-a",
                )
                self.assertEqual(readback.status, "attention-required")
                self.assertEqual(readback.execution, "succeeded")
                self.assertEqual(readback.advancement, "unverified")
                self.assertEqual(readback.next_public_read, "read.current-graph")

    def test_status_reads_truth_during_writer_lock_and_never_rebinds_target(self) -> None:
        from control_plane_kit_servers_cpk_server.client import JournalError, TopologyClient

        transport = ScriptedTransport(destructive=True)
        client = self.client(transport)
        planned = client.plan(self.desired_path)
        journal_path = client.journal.root / f"{planned.operation_ref}.json"
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        journal["last_result"]["changes"][0]["operation"] = "create-node"
        journal["last_result"]["required_scope"] = "plan:approve"
        journal["last_result"]["destructive"] = False
        journal_path.write_text(json.dumps(journal), encoding="utf-8")
        calls_before = len(transport.calls)

        with client.journal.mutation_lock(planned.operation_ref):
            status = client.status(planned.operation_ref)
            with self.assertRaises(JournalError):
                with client.journal.mutation_lock(planned.operation_ref):
                    pass

        mismatched = TopologyClient(
            self.profile(endpoint="https://other.example"),
            transport=transport,
            journal=client.journal,
        )
        with self.assertRaises(JournalError):
            mismatched.status(planned.operation_ref)

        self.assertEqual(status.status, "planned")
        self.assertEqual(status.changes[0]["operation"], "delete-node")
        self.assertEqual(status.required_scope, "plan:approve-destructive")
        self.assertIs(status.destructive, True)
        status_calls = transport.calls[calls_before:]
        self.assertTrue(status_calls)
        self.assertTrue(all(call["route_id"].startswith("read.") for call in status_calls))

    def test_journal_lock_paths_bounds_secrets_and_unresolved_retention(self) -> None:
        from control_plane_kit_servers_cpk_server.client import JournalError

        transport = ScriptedTransport(lose_prepare_once=True)
        client = self.client(transport)
        unresolved = client.plan(self.desired_path)
        journal_path = (
            client.journal.root / f"{unresolved.operation_ref}.json"
        )
        raw = journal_path.read_text(encoding="utf-8")
        document = json.loads(raw)

        semantic_corruption = dict(document)
        semantic_corruption["phase"] = "converged"
        semantic_corruption["pending_request"] = None
        journal_path.write_text(json.dumps(semantic_corruption), encoding="utf-8")
        calls_before_corruption = tuple(transport.calls)
        with self.assertRaises(JournalError):
            client.status(unresolved.operation_ref)
        self.assertEqual(tuple(transport.calls), calls_before_corruption)
        journal_path.write_text(raw, encoding="utf-8")

        self.assertNotIn("Hello", raw)
        self.assertNotIn("secret://hello/token", raw)
        self.assertEqual(document["desired"]["sha256"], _sha256(self.desired_path))
        self.assertIsNotNone(document["pending_request"])
        self.assertTrue(journal_path.exists())
        partial = journal_path.with_suffix(".json.part")
        partial.symlink_to(self.desired_path)
        with self.assertRaises(JournalError):
            client.journal.write(unresolved.operation_ref, document)
        self.assertTrue(partial.is_symlink())
        partial.unlink()
        oversized = dict(document)
        oversized["last_result"] = {"value": "x" * 1_048_576}
        with self.assertRaises(JournalError):
            client.journal.write(unresolved.operation_ref, oversized)
        self._assert_profile_and_cli_contract()
        journal_path.write_text("{", encoding="utf-8")
        with self.assertRaises(JournalError):
            client.status(unresolved.operation_ref)


def _sha256(path: Path) -> str:
    from hashlib import sha256

    return sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
