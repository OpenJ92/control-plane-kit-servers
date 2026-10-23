"""S2 production composition laws; no database or external effects are needed."""
import importlib
import importlib.util
import unittest
from dataclasses import fields
from unittest.mock import Mock, patch


class OperationsApplicationFactoryTests(unittest.TestCase):
    def test_shared_factory_preserves_owner_sharing_and_id_domains(self):
        name = "control_plane_kit_servers_cpk_server.operations_application"
        self.assertIsNotNone(importlib.util.find_spec(name),
            "the production and maintained public witness need one owner factory")
        composition = importlib.import_module(name)
        unit_of_work = Mock(name="uow-must-not-open-during-composition")
        ids = composition.OperationsIdFactories(
            service=Mock(name="service-id"), lifecycle=Mock(name="lifecycle-id"),
            start=Mock(name="start-id"), fold=Mock(name="fold-id"),
            coordinator=Mock(name="coordinator-id"))
        clock = Mock(name="clock")
        decoders, health, observer = object(), object(), object()
        runtime, ingress = {}, {}
        probes = Mock(name="gateway-probe-builder", return_value=object())
        self.assertIn("secret_metadata_reader", {item.name for item in fields(composition.OperationsEffectPorts)},
            "shared production factory must admit the existing Operations metadata port")
        metadata = object()
        ports = composition.OperationsEffectPorts(runtime, ingress, health, decoders, observer,
            secret_metadata_reader=metadata)
        with patch.multiple(composition,
                RunLifecycleCommandService=Mock(), EffectAttemptStartService=Mock(),
                EffectAttemptFoldService=Mock(), EffectAttemptReconciliationService=Mock(),
                HealthSigningAuthorityReloadService=Mock(), ExecutionCoordinator=Mock(),
                SecretUseAuthorizationService=Mock(), RuntimeInterpreterDispatcher=Mock(),
                IngressRealizationAdapter=Mock(), ActivityExecutionDispatcher=Mock(),
                ActivityPlanningCommandService=Mock(), WorkspaceCommandService=Mock(),
                DesiredTopologyDraftCommandService=Mock(), DesiredGraphCommandService=Mock(),
                ApprovalCommandService=Mock(), ExecutionAdmissionCommandService=Mock(),
                OperationCommandService=Mock(), CurrentGraphAdvancementCommandService=Mock(),
                cpk_server_services=Mock(), CpkServerOperationsApplication=Mock()) as unused:
            result = composition.OperationsApplicationFactory(unit_of_work, ports, ids,
                clock=clock, gateway_probe_factory=probes)()
            lifecycle = composition.RunLifecycleCommandService
            start = composition.EffectAttemptStartService
            fold = composition.EffectAttemptFoldService
            reconciliation = composition.EffectAttemptReconciliationService
            reload = composition.HealthSigningAuthorityReloadService
            coordinator = composition.ExecutionCoordinator
            authorizer = composition.SecretUseAuthorizationService
            authorizer.assert_called_once_with(unit_of_work)
            lifecycle.assert_called_once_with(unit_of_work, clock=clock, id_factory=ids.lifecycle)
            start.assert_called_once_with(unit_of_work, id_factory=ids.start,
                health_receiver_decoders=decoders)
            fold.assert_called_once_with(unit_of_work, id_factory=ids.fold)
            reload.assert_called_once_with(unit_of_work, health_receiver_decoders=decoders)
            reconciliation.assert_called_once_with(unit_of_work, observer, fold.return_value)
            composition.RuntimeInterpreterDispatcher.assert_called_once_with(runtime,
                secret_use_authorizer=authorizer.return_value)
            composition.IngressRealizationAdapter.assert_called_once_with(unit_of_work,
                interpreters=ingress, clock=clock, secret_use_authorizer=authorizer.return_value)
            composition.ActivityExecutionDispatcher.assert_called_once_with(
                runtime=composition.RuntimeInterpreterDispatcher.return_value,
                ingress=composition.IngressRealizationAdapter.return_value)
            coordinator.assert_called_once_with(unit_of_work,
                lifecycle=lifecycle.return_value,
                adapter=composition.ActivityExecutionDispatcher.return_value,
                start_service=start.return_value, fold_service=fold.return_value,
                reconciliation_service=reconciliation.return_value, clock=clock,
                id_factory=ids.coordinator, managed_health=health,
                health_signing_authority=reload.return_value)
            probes.assert_called_once_with(unit_of_work, authorizer.return_value)
            for service in ("ActivityPlanningCommandService", "WorkspaceCommandService",
                    "DesiredTopologyDraftCommandService",
                    "ApprovalCommandService", "ExecutionAdmissionCommandService",
                    "OperationCommandService", "CurrentGraphAdvancementCommandService"):
                getattr(composition, service).assert_called_once_with(unit_of_work,
                    clock=clock, id_factory=ids.service)
            composition.DesiredGraphCommandService.assert_called_once_with(unit_of_work,
                clock=clock, id_factory=ids.service, secret_metadata_reader=metadata)
            services = composition.cpk_server_services.call_args.kwargs
            self.assertIs(services["gateway_probes"], probes.return_value)
            self.assertIs(services["lifecycle"], lifecycle.return_value)
            self.assertIs(services["execution"], coordinator.return_value)
            self.assertIs(services["unit_of_work_factory"], unit_of_work)
            self.assertIsNone(services["delegation_key_generation"])
            self.assertEqual(set(services), {
                "unit_of_work_factory", "planning", "workspaces", "products",
                "image_pull_authorities", "runtime_authorities", "ingress_authorities",
                "secret_providers", "delegation_signing_keys", "delegation_key_generation", "desired_topology_drafts",
                "desired_graphs", "approval", "admission", "lifecycle", "operations",
                "execution", "advancement", "gateway_probes", "clock"})
            self.assertIs(result, composition.CpkServerOperationsApplication.return_value)
        unit_of_work.assert_not_called()

    def test_entrypoint_and_public_witness_delegate_to_shared_factory(self):
        from control_plane_kit_servers_cpk_server import server
        import receiver_acceptance_operations as witness
        name = "control_plane_kit_servers_cpk_server.operations_application"
        self.assertIsNotNone(importlib.util.find_spec(name),
            "shared production factory is not implemented")
        composition = importlib.import_module(name)
        self.assertIs(server.OperationsApplicationFactory, composition.OperationsApplicationFactory)
        self.assertIs(witness.SharedOperationsApplicationFactory, composition.OperationsApplicationFactory)
        config = Mock()
        config.managed_health_process = None
        with patch.object(server, "_install_operations_schema") as schema, \
                patch.object(server, "_secret_provider_composition") as provider, \
                patch.object(server, "_operations_effect_ports") as effect_ports, \
                patch.object(server, "OperationsApplicationFactory") as production:
            self.assertIs(server._operations_application(config), production.return_value.return_value)
            schema.assert_called_once_with(config.operations_database_url.return_value)
            provider.assert_called_once_with(config)
            effect_ports.assert_called_once_with(config, provider.return_value)
            self.assertIs(production.call_args.args[1], effect_ports.return_value)
            actual_ids = production.call_args.args[2]
            for field, expected in (("service", server._id), ("lifecycle", server._lifecycle_id),
                    ("start", server._start_id), ("fold", server._fold_id),
                    ("coordinator", server._coordinator_id)):
                self.assertIs(getattr(actual_ids, field), expected)
            self.assertIs(production.call_args.kwargs["clock"], server._clock)
        uow, health, decoders = Mock(), object(), object()
        ids, clock = Mock(), Mock()
        with patch.object(witness, "SharedOperationsApplicationFactory") as shared:
            factory = witness.OperationsApplicationFactory(uow,
                witness.OperationsEffectPorts({}, {}, health, decoders), ids, clock)
            self.assertIs(factory(), shared.return_value.return_value)
            arguments = shared.call_args
            self.assertIs(arguments.args[0], uow)
            self.assertIs(arguments.args[1].managed_health, health)
            self.assertIs(arguments.args[1].health_receiver_decoders, decoders)
            self.assertIs(arguments.kwargs["clock"], clock)
            for field in ("service", "start", "fold", "lifecycle", "coordinator"):
                self.assertIs(getattr(arguments.args[2], field), ids)
