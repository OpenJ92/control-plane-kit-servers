from __future__ import annotations

import importlib
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.topology import GraphDescriptorCodec, compile_topology
from control_plane_kit_servers_cpk_server import installation as shared
from control_plane_kit_servers_cpk_server.client import ClientProfile, ClientResult
import test_docker_installation as composition_laws


class RecordingClient:
    def __init__(self, root, workspace, endpoint):
        self.profile = ClientProfile(endpoint, workspace,
            {role: root / 'credential' for role in ('operator', 'approver', 'worker')}, root / 'client')
        self.transport = self
        self.calls = []
        self.plan_graph = None
        self.lose_route = None
        self.corrupt_product = False
        self.provider_registration = 'provider-returned-17'
        self.current = 'current-child-3'
        self.desired = 'desired-child-5'

    def plan(self, path, *, title):
        self.plan_graph = json.loads(path.read_text())
        self.calls.append(('client.plan', {}, {}))
        return ClientResult('planned', '11111111-1111-4111-8111-111111111111',
                            self.profile.workspace_id, plan_id='plan-child-7')

    def call(self, route_id, *, path_parameters, payload, credential_role):
        self.calls.append((route_id, dict(path_parameters), dict(payload)))
        if route_id == self.lose_route:
            raise RuntimeError('private-provider-response-must-not-escape')
        workspace = self.profile.workspace_id
        if route_id == 'command.product.import':
            document = ProductDescriptorCodec().decode_document(payload['descriptor_document'])
            reference = ProductReference.from_document(document).descriptor()
            return {'registration_id': 'product-13', 'workspace_id': workspace,
                    'status': 'active', 'reference': {} if self.corrupt_product else reference}
        if route_id == 'command.workspace.create':
            return {'replayed': False, 'workspace': {'workspace_id': workspace,
                    'current_graph_id': self.current, 'desired_graph_id': self.desired}}
        if route_id == 'read.workspace':
            return {'workspace_id': workspace, 'current_graph_id': self.current,
                    'desired_graph_id': self.desired}
        if route_id == 'read.current-graph':
            return {'workspace_id': workspace, 'graph_id': self.current, 'assigned': True}
        if route_id == 'read.desired-graph':
            return {'workspace_id': workspace, 'graph_id': self.desired, 'assigned': True}
        if route_id == 'command.secret-provider.register':
            return {'registration_id': self.provider_registration, 'workspace_id': workspace}
        if route_id == 'read.secret-provider-detail':
            return {'workspace_id': workspace, 'secret_provider': {'registration_id': self.provider_registration}}
        if route_id == 'command.secret-reference.register':
            return {'registration_id': 'reference-19', 'workspace_id': workspace}
        if route_id == 'read.secret-reference-detail':
            return {'workspace_id': workspace, 'secret_reference': {'registration_id': 'reference-19'}}
        if route_id == 'command.runtime-authority.register':
            return {'registration_id': 'runtime-23', 'workspace_id': workspace}
        if route_id == 'read.runtime-authority-detail':
            return {'workspace_id': workspace, 'runtime_authority': {'registration_id': 'runtime-23'}}
        if route_id == 'command.runtime-authority-delivery.register':
            return {'delivery_id': 'delivery-29', 'workspace_id': workspace}
        if route_id == 'read.runtime-authority-delivery-detail':
            return {'workspace_id': workspace, 'runtime_authority_delivery': {'delivery_id': 'delivery-29'}}
        raise AssertionError('unexpected public route')


class ChildInstallationClientTests(unittest.TestCase):
    def api(self):
        name = 'control_plane_kit_servers_cpk_server.client.installation'
        try:
            return importlib.import_module(name)
        except ModuleNotFoundError as error:
            if error.name != name:
                raise
            self.fail('public child installation recipe is not implemented')

    def installation(self):
        value = composition_laws.DockerInstallationTests().installation(shared)
        scopes = tuple(PolicyScope(value) for value in (
            'hub:instance:create', 'instance:workspace:read', 'instance:workspace:edit',
            'secret-provider:register', 'secret-provider:read',
            'runtime-authority:register', 'runtime-authority:read',
            'runtime-authority-delivery:register', 'runtime-authority-delivery:read',
            'plan:request', 'plan:approve', 'plan:execute', 'execution:operate'))
        return replace(value, workspace_grants=(WorkspaceGrant('child-workspace', scopes),))

    def setup(self):
        return {'workspace_name': 'Child workspace', 'provider': {
            'provider_id': 'control-plane-kit',
            'allowed_reference_prefixes': ['secret://child/application'],
            'allowed_intents': ['application.control-token']},
            'secret_references': [{'reference': 'secret://child/application/token',
                                   'allowed_intents': ['application.control-token']}]}

    def test_document_is_exact_shared_graph_and_composed_variant_imports(self):
        api = self.api()
        value = self.installation()
        document = api.child_installation_document(value, child_workspace_id='child-workspace')
        topology = shared.compose_docker_cpk_installation(value)
        self.assertEqual(document['graph'], GraphDescriptorCodec().encode(compile_topology(topology)))
        expected = [child.implementation.document for child in topology.root.children
                    if hasattr(child, 'block_id')]
        self.assertEqual(document['products'], [json.loads(item.content) for item in expected])
        self.assertEqual(document['child_endpoint'], 'https://child-a.example.test')
        self.assertEqual(document['parent_workspace_id'], 'parent-workspace')
        self.assertEqual(document['child_workspace_id'], 'child-workspace')
        with self.assertRaises(api.ChildInstallationError):
            api.child_installation_document(replace(value, ingress=shared.ExternalInstallationIngress(
                'https://child-a.example.test'), connector_product=None), child_workspace_id='child-workspace')

    def test_parent_imports_exact_variants_before_existing_client_plan(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = RecordingClient(root, 'parent-workspace', 'http://127.0.0.1:18080')
            value = self.installation()
            result = api.prepare_child_installation(value, parent=parent,
                child_workspace_id='child-workspace', state_directory=root / 'prepare')
            expected = api.child_installation_document(value, child_workspace_id='child-workspace')
            self.assertEqual(parent.plan_graph, expected['graph'])
            self.assertEqual([call[2]['descriptor_document'] for call in parent.calls[:-1]], expected['products'])
            self.assertTrue(all(call[0] == 'command.product.import' for call in parent.calls[:-1]))
            self.assertEqual(parent.calls[-1][0], 'client.plan')
            self.assertEqual(result.plan_id, 'plan-child-7')
            self.assertFalse(any('actor_scopes' in call[2] for call in parent.calls))

    def test_child_setup_binds_actual_provider_and_reads_child_truth(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = RecordingClient(root, 'child-workspace', 'https://child-a.example.test')
            result = api.initialize_child_workspace(self.installation(), child=child,
                setup=self.setup(), state_directory=root / 'setup')
            self.assertEqual(result['status'], 'child-initialized')
            self.assertEqual(result['workspace_id'], 'child-workspace')
            registered = [call for call in child.calls if call[0] == 'command.secret-reference.register']
            self.assertEqual(registered[0][2]['provider_registration_id'], child.provider_registration)
            self.assertTrue(all(call[1]['workspace_id'] == 'child-workspace' for call in child.calls))
            self.assertTrue({'read.workspace', 'read.current-graph', 'read.desired-graph'} <= {call[0] for call in child.calls})
            self.assertFalse(any('actor_scopes' in call[2] for call in child.calls))

    def test_wrong_target_or_scope_refused_before_any_mutation(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for workspace, endpoint in (('other-workspace', 'https://child-a.example.test'),
                                        ('child-workspace', 'https://other.example.test')):
                child = RecordingClient(root, workspace, endpoint)
                with self.assertRaises(api.ChildInstallationError):
                    api.initialize_child_workspace(self.installation(), child=child,
                        setup=self.setup(), state_directory=root / 'absent')
                self.assertEqual(child.calls, [])
                self.assertFalse((root / 'absent').exists())
            value = replace(self.installation(), workspace_grants=(
                WorkspaceGrant('child-workspace', (PolicyScope.INSTANCE_WORKSPACE_READ,)),))
            child = RecordingClient(root, 'child-workspace', 'https://child-a.example.test')
            with self.assertRaises(api.ChildInstallationError):
                api.initialize_child_workspace(value, child=child, setup=self.setup(), state_directory=root / 'absent')
            self.assertEqual(child.calls, [])

    def test_lost_response_holds_without_redispatch_or_private_body(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = RecordingClient(root, 'child-workspace', 'https://child-a.example.test')
            child.lose_route = 'command.runtime-authority.register'
            state = root / 'setup'
            with self.assertRaises(api.ChildInstallationHold) as caught:
                api.initialize_child_workspace(self.installation(), child=child, setup=self.setup(), state_directory=state)
            self.assertNotIn('private-provider-response', str(caught.exception))
            receipt = state / 'progress.json'
            before = receipt.read_bytes()
            self.assertIn(child.provider_registration, before.decode())
            self.assertNotIn('private-provider-response', before.decode())
            calls = list(child.calls)
            with self.assertRaises(api.ChildInstallationHold):
                api.initialize_child_workspace(self.installation(), child=child, setup=self.setup(), state_directory=state)
            self.assertEqual(child.calls, calls)
            self.assertEqual(receipt.read_bytes(), before)
            parent = RecordingClient(root, 'parent-workspace', 'http://127.0.0.1:18080')
            parent.corrupt_product = True
            with self.assertRaises(api.ChildInstallationHold):
                api.prepare_child_installation(self.installation(), parent=parent,
                    child_workspace_id='child-workspace', state_directory=root / 'prepare')
            self.assertIsNone(parent.plan_graph)
            self.assertEqual(len(parent.calls), 1)
