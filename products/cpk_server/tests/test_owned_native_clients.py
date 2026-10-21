"""Owned native observation custody; no provider or admitted-history simulation."""
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from docker.transport import UnixHTTPAdapter
from control_plane_kit_interpreters.docker.sdk import DockerSdkClient, DockerUnixSocketClientConfig
from control_plane_kit_interpreters.docker.connector_connection import DockerConnectorConnectionObserver
from control_plane_kit_operations.effect_outcome_evidence import (
    NativeConnectionObservation, NativeConnectionOutcome, NativeConnectionRefused,
)
from control_plane_kit_operations.runtime_authorities import RegisteredRuntimeAuthorityStatus
from managed_native_material import NativeMaterial


class OwnedNativeClientTests(unittest.TestCase):
    def setUp(self):
        from control_plane_kit_servers_cpk_server import managed_health_placement as placement
        self.assertTrue(callable(getattr(placement, "DockerRuntimePolicyBinding", None)),
            "scoped owned Docker policy binding is missing")
        self.placement = placement
        self.policy = DockerUnixSocketClientConfig("/var/run/cpk-owned-test.sock", 5.0)
        self.world = NativeMaterial()
        self.clock = Mock(return_value=datetime(2026, 10, 20, tzinfo=timezone.utc))
        self.events = []
        self.raws = []

    def native(self, world=None):
        from control_plane_kit_servers_cpk_server.managed_native_connection import DockerManagedNativeConnection
        world = world or self.world
        binding = self.placement.DockerRuntimePolicyBinding("workspace-a", "docker",
            world.authority.authority_ref, self.policy)
        selector = self.placement.DockerRuntimeClientSelector((binding,))
        return DockerManagedNativeConnection(selector, world.document, self.clock)

    def record(self, name):
        self.events.append((name, threading.get_ident()))

    def raw(self, *, read=None, version_error=False, close_error=False):
        api = Mock()
        api.timeout = 5.0
        api.base_url = "http+docker://localhost"
        api.get_adapter.return_value = UnixHTTPAdapter("http+unix://" + self.policy.socket_path)
        def inspect(*args, **kwargs):
            self.record("read")
            if read is not None:
                read()
            raise RuntimeError("private provider read detail")
        api.inspect_container.side_effect = inspect
        def version(**kwargs):
            self.record("version")
            self.assertEqual(kwargs, {"api_version": False})
            if version_error:
                raise RuntimeError("private handshake detail")
            return {"MinAPIVersion": "1.24", "ApiVersion": "1.55"}
        def close():
            self.record("close")
            if close_error:
                raise RuntimeError("private close detail")
        raw = SimpleNamespace(api=api, version=Mock(side_effect=version), close=Mock(side_effect=close))
        self.raws.append(raw)
        return raw

    def factory(self, **raw_options):
        def construct(**kwargs):
            self.record("construct")
            self.assertEqual(kwargs, {"base_url": "unix://" + self.policy.socket_path,
                "timeout": 5.0, "version": "1.45"})
            return self.raw(**raw_options)
        return construct

    def observe(self, world=None, native=None):
        world = world or self.world
        return asyncio.run((native or self.native(world)).observe_connection(
            world.realization, world.request, world.authority))

    def assert_unknown(self, result, world=None):
        world = world or self.world
        self.assertEqual(result, NativeConnectionObservation(NativeConnectionOutcome.UNKNOWN,
            world.request.effect_id, world.request.activity_id.value))

    def test_policy_selection_is_pure_scoped_and_redacted(self):
        with patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
            for options in ({}, {"retained": True}, {"retained_image": True}):
                world = NativeMaterial(**options)
                native = self.native(world)
                self.assertEqual(native.select(**world.selection()), (world.request.activity_id,))
                selector = native.provider_clients
                binding, = selector.bindings
                self.assertIs(binding.local_client_config, self.policy)
                for changes in (dict(workspace_id="foreign"), dict(runtime_id="foreign"),
                        dict(authority=replace(world.authority, status=RegisteredRuntimeAuthorityStatus.REVOKED)),
                        dict(authority=replace(world.authority, workspace_id="foreign"))):
                    arguments = dict(workspace_id="workspace-a", runtime_id="docker", authority=world.authority)
                    self.assertIsNone(selector.select(**dict(arguments, **changes)))
                self.assertNotIn(self.policy.socket_path, repr(binding))
                with self.assertRaises(AttributeError):
                    binding.runtime_id = "changed"
            constructor.assert_not_called()
            ambient.assert_not_called()
        self.clock.assert_not_called()

    def test_closed_binding_union_rejects_cross_kind_duplicates_and_invalid_policies(self):
        binding, = self.native().provider_clients.bindings
        client = DockerSdkClient(client=SimpleNamespace(api=Mock()), connect_on_init=False)
        borrowed = self.placement.DockerRuntimeClientBinding("workspace-a", "docker",
            self.world.authority.authority_ref, client)
        for values in ((binding, replace(binding)), (binding, borrowed),
                tuple(replace(binding, runtime_id="runtime-" + str(i)) for i in range(65)), (Mock(),)):
            with self.assertRaises(ValueError):
                self.placement.DockerRuntimeClientSelector(values)
        for policy in (None, Mock(), "/var/run/private.sock"):
            with self.assertRaises(ValueError) as raised:
                replace(binding, local_client_config=policy)
            self.assertNotIn("private.sock", str(raised.exception))
        self.assertEqual(self.placement.DockerRuntimeClientSelector((binding,)).bindings, (binding,))

    def test_owned_policy_does_not_supply_local_placement_or_an_independent_selector(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthBootstrap, ManagedHealthUnavailable
        world = NativeMaterial(retained=True)
        native = self.native(world)
        bridge = ManagedHealthBootstrap((world.authored.documents["gateway"],), native.provider_clients,
            endpoints=None, native=native).build(Mock())
        binding, = native.provider_clients.bindings
        with self.assertRaises(ValueError):
            self.placement.DockerControllerPlacement(binding, "c" * 64)
        with self.assertRaises(ValueError):
            replace(bridge, native=replace(native,
                provider_clients=self.placement.DockerRuntimeClientSelector((binding,))))
        with patch("docker.DockerClient") as constructor:
            self.assertIsNone(bridge.select(**world.selection()))
            with self.assertRaises(ManagedHealthUnavailable):
                asyncio.run(bridge.observe_connection(world.realization, world.request, world.authority))
            constructor.assert_not_called()

    def test_real_observer_acquires_reads_and_closes_in_one_worker(self):
        caller = threading.get_ident()
        with patch("docker.DockerClient", side_effect=self.factory()) as constructor, patch("docker.from_env") as ambient:
            self.assert_unknown(self.observe())
        constructor.assert_called_once()
        ambient.assert_not_called()
        self.assertEqual([name for name, _ in self.events], ["construct", "version", "read", "close"])
        self.assertEqual(len({thread for _, thread in self.events}), 1)
        self.assertNotEqual(self.events[0][1], caller)
        self.raws[0].close.assert_called_once_with()

    def test_missing_foreign_and_malformed_retained_proof_refuse_before_contact(self):
        for options in ({"retained": True}, {"retained_image": True}):
            for kind in ("missing", "foreign", "malformed"):
                with self.subTest(options=options, kind=kind):
                    world = NativeMaterial(**options)
                    original = world.realization.connector_installation
                    if kind == "missing":
                        installation = None
                    elif kind == "foreign":
                        foreign = replace(original.original_request,
                            source=replace(original.original_request.source, workspace_id="foreign"))
                        installation = SimpleNamespace(original_request=foreign, receipt=original.receipt)
                    else:
                        installation = SimpleNamespace(original_request=original.original_request, receipt=object())
                    world.realization.connector_installation = installation
                    with patch("docker.DockerClient") as constructor, patch("docker.from_env") as ambient:
                        self.assertEqual(self.observe(world), NativeConnectionRefused())
                        constructor.assert_not_called()
                        ambient.assert_not_called()
        self.clock.assert_not_called()

    def test_valid_retained_original_pair_reaches_observer_and_keeps_current_correlation(self):
        for options in ({"retained": True}, {"retained_image": True}):
            with self.subTest(options=options):
                world = NativeMaterial(**options)
                self.assertNotEqual(world.realization.connector_installation.original_request.effect_id,
                    world.request.effect_id)
                with patch("docker.DockerClient", side_effect=self.factory()):
                    self.assert_unknown(self.observe(world), world)
                self.raws[-1].api.inspect_container.assert_called_once()
                self.raws[-1].close.assert_called_once_with()

    def test_failed_deferred_acquisition_keeps_unknown_and_closes_raw_handle_once(self):
        with patch("docker.DockerClient", side_effect=self.factory(version_error=True)) as constructor:
            self.assert_unknown(self.observe())
        constructor.assert_called_once()
        self.raws[0].api.inspect_container.assert_not_called()
        self.raws[0].close.assert_called_once_with()
        self.assertEqual([name for name, _ in self.events], ["construct", "version", "close"])

    def test_final_close_failure_is_fixed_unavailable(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        with patch("docker.DockerClient", side_effect=self.factory(close_error=True)):
            with self.assertRaises(ManagedHealthUnavailable) as raised:
                self.observe()
        self.assertEqual(str(raised.exception), "managed health is unavailable")
        self.assertIsNone(raised.exception.__context__)
        self.raws[0].close.assert_called_once_with()

    def test_worker_escaping_error_closes_owned_wrapper_without_exposing_detail(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        # The actual wrapper remains lazy; an escaped observer error before its
        # first read owns a wrapper but has no raw Docker handle to close.
        closed = []
        original_close = DockerSdkClient.close
        def close(client):
            closed.append(client)
            return original_close(client)
        with patch.object(DockerConnectorConnectionObserver, "observe", side_effect=RuntimeError("private detail")), \
                patch.object(DockerSdkClient, "close", close), patch("docker.DockerClient") as constructor:
            with self.assertRaises(ManagedHealthUnavailable) as raised:
                self.observe()
        self.assertEqual(len(closed), 1)
        self.assertEqual(str(raised.exception), "managed health is unavailable")
        self.assertIsNone(raised.exception.__context__)
        constructor.assert_not_called()

    def test_request_authority_mismatch_refuses_before_acquisition(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        with patch("docker.DockerClient") as constructor:
            with self.assertRaises(ManagedHealthUnavailable):
                asyncio.run(self.native().observe_connection(self.world.realization, self.world.request,
                    replace(self.world.authority, registration_id="replaced")))
            constructor.assert_not_called()

    def test_cancelled_caller_does_not_close_blocked_worker_or_receive_late_success(self):
        async def scenario():
            loop = asyncio.get_running_loop()
            entered, finished = asyncio.Event(), asyncio.Event()
            release = threading.Event()
            def read():
                loop.call_soon_threadsafe(entered.set)
                if not release.wait(5):
                    raise AssertionError("bounded test release was not delivered")
            def construct(**kwargs):
                raw = self.factory(read=read)(**kwargs)
                prior = raw.close.side_effect
                def close():
                    try:
                        prior()
                    finally:
                        loop.call_soon_threadsafe(finished.set)
                raw.close.side_effect = close
                return raw
            with patch("docker.DockerClient", side_effect=construct) as constructor:
                task = asyncio.create_task(self.native().observe_connection(
                    self.world.realization, self.world.request, self.world.authority))
                try:
                    await asyncio.wait_for(entered.wait(), 5)
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await asyncio.wait_for(task, 1)
                    self.raws[0].close.assert_not_called()
                finally:
                    release.set()
                    await asyncio.wait_for(finished.wait(), 5)
                self.assertTrue(task.cancelled())
                constructor.assert_called_once()
                self.raws[0].close.assert_called_once_with()
                self.raws[0].api.inspect_container.assert_called_once()
        asyncio.run(scenario())
        self.assertEqual(len({thread for _, thread in self.events}), 1)

    def test_overlapping_calls_own_distinct_clients_and_each_close_once(self):
        async def scenario():
            loop = asyncio.get_running_loop()
            both = asyncio.Event()
            release = threading.Event()
            lock = threading.Lock()
            arrivals = 0
            def read():
                nonlocal arrivals
                with lock:
                    arrivals += 1
                    if arrivals == 2:
                        loop.call_soon_threadsafe(both.set)
                if not release.wait(5):
                    raise AssertionError("bounded test release was not delivered")
            with patch("docker.DockerClient", side_effect=self.factory(read=read)) as constructor:
                native = self.native()
                tasks = [asyncio.create_task(native.observe_connection(
                    self.world.realization, self.world.request, self.world.authority)) for _ in range(2)]
                try:
                    await asyncio.wait_for(both.wait(), 5)
                    self.assertEqual(len(self.raws), 2)
                    self.assertIsNot(self.raws[0], self.raws[1])
                    for raw in self.raws:
                        raw.close.assert_not_called()
                finally:
                    release.set()
                    results = await asyncio.wait_for(asyncio.gather(*tasks), 5)
                for result in results:
                    self.assert_unknown(result)
                self.assertEqual(constructor.call_count, 2)
                for raw in self.raws:
                    raw.close.assert_called_once_with()
        asyncio.run(scenario())

    def test_borrowed_client_remains_open_when_observation_escapes(self):
        from control_plane_kit_servers_cpk_server.managed_health import ManagedHealthUnavailable
        native = self.native()
        raw = self.raw()
        client = DockerSdkClient(client=raw, connect_on_init=False)
        binding = self.placement.DockerRuntimeClientBinding("workspace-a", "docker",
            self.world.authority.authority_ref, client)
        native = replace(native, provider_clients=self.placement.DockerRuntimeClientSelector((binding,)))
        with patch.object(DockerConnectorConnectionObserver, "observe", side_effect=RuntimeError("private")):
            with self.assertRaises(ManagedHealthUnavailable):
                self.observe(native=native)
        raw.close.assert_not_called()
