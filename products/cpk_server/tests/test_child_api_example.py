"""Composition laws only; actual joined acceptance belongs to live_child_api."""

from hashlib import sha256
from contextlib import nullcontext
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from control_plane_kit_core.topology import DeploymentGraph, GraphDescriptorCodec
from control_plane_kit_servers_cpk_server.client import ClientResult, SavedDesiredRevision
from control_plane_kit_servers_cpk_server.client.installation import ChildInstallationHold, child_installation_document
from products.cpk_server.examples import public_child_api as recipe
import test_child_installation_client as composition


class ChildApiExampleTests(unittest.TestCase):
    def setUp(self):
        self.hello_modules = {name for name in sys.modules
                             if name == 'control_plane_kit_servers_hello_server'
                             or name.startswith('control_plane_kit_servers_hello_server.')}

    def tearDown(self):
        for name in tuple(sys.modules):
            if name not in self.hello_modules and (name == 'control_plane_kit_servers_hello_server'
                    or name.startswith('control_plane_kit_servers_hello_server.')):
                sys.modules.pop(name)

    def test_generated_fixture_operations_match_before_any_approval(self):
        from copy import deepcopy
        from control_plane_kit_core.delegation_authority import DelegationAuthorityBinding
        from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
        from control_plane_kit_core.products import ProductDescriptorCodec
        from control_plane_kit_core.public_ingress import IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget
        from control_plane_kit_core.planning import ActivityPlanDescriptorCodec, compile_activity_plan
        from control_plane_kit_core.topology import diff_graphs, validate_graph
        from products.cpk_server.tests import live_child_api as witness

        installation = composition.ChildInstallationClientTests().installation()
        installation_graph = GraphDescriptorCodec().decode(child_installation_document(
            installation, child_workspace_id='child-workspace')['graph'])
        source = Path(__file__).resolve().parents[3]
        products = {name: ProductDescriptorCodec().decode_document(
            (source / 'products' / name / 'product.cpk.json').read_bytes()).product
            for name in ('hello_server', 'http_active_router', 'cpk_local_gateway', 'cloudflared_connector')}
        prefix = installation.installation_id
        proof_graph = recipe.child_application_graph(installation, 'child-workspace',
            hello_product=products['hello_server'], router_product=products['http_active_router'],
            gateway_product=products['cpk_local_gateway'], connector_product=products['cloudflared_connector'],
            ingress=NamedPublicIngress(prefix + '-gateway-public', IngressAuthorityReference('application-cloudflare'),
                PublicIngressTarget(prefix + '-gateway', 'control'), prefix + '-gateway-connector',
                'fresh-run-gateway.example.test'),
            delegation_authority=DelegationAuthorityBinding(prefix + '-gateway',
                DelegationKeyPurpose.GATEWAY_PROBE, 'acceptance-issuer'))
        for graph in (installation_graph, proof_graph):
            for destructive in (False, True):
                with self.subTest(graph=graph.name, destructive=destructive):
                    empty = DeploymentGraph(graph.name)
                    before, after = (graph, empty) if destructive else (empty, graph)
                    payload = ActivityPlanDescriptorCodec().encode(compile_activity_plan(
                        diff_graphs(validate_graph(before), validate_graph(after))))
                    detail = {'plan_id': 'plan-1', 'payload': payload}
                    calls = []
                    def call(route, **arguments):
                        self.assertEqual(route, 'read.plan-detail')
                        self.assertEqual(arguments['path_parameters']['plan_id'], 'plan-1')
                        return {'plan': detail}
                    def apply(operation_ref, **arguments):
                        calls.append((operation_ref, arguments))
                        return SimpleNamespace(status='converged', execution='succeeded', advancement='advanced')
                    client = SimpleNamespace(profile=SimpleNamespace(workspace_id='workspace'),
                                             transport=SimpleNamespace(call=call), apply=apply)
                    prepared = ClientResult('planned', 'operation-1', 'workspace', plan_id='plan-1',
                                            destructive=destructive, changes=({'operation': 'present'},))
                    witness.apply_reviewed(client, prepared, destructive=destructive, fixture_graph=graph)
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(calls[0][1], {'execute_plan': 'plan-1',
                        'approve_destructive_plan' if destructive else 'approve_plan': 'plan-1'})
                    calls.clear()
                    # Extra foreign target/action and missing/duplicate effects
                    # must all stop before the approval/execution client call.
                    for corruption in ('target', 'action', 'missing', 'duplicate'):
                        altered = deepcopy(payload)
                        if corruption == 'missing':
                            altered['activities'].pop()
                        else:
                            extra = deepcopy(altered['activities'][0])
                            if corruption == 'target':
                                target = extra['operation']['target']
                                coordinate = next(key for key in target if key != 'kind')
                                target[coordinate] = 'unrelated-resource'
                            elif corruption == 'action':
                                extra['operation']['kind'] = 'unexpected-action'
                            altered['activities'].append(extra)
                        detail['payload'] = altered
                        with self.assertRaisesRegex(AssertionError, 'released fixture transition'):
                            witness.apply_reviewed(client, prepared, destructive=destructive, fixture_graph=graph)
                        self.assertEqual(calls, [])

    def test_supplied_parent_endpoint_must_match_actual_root_before_child_mutation(self):
        from products.cpk_server.tests import live_child_api as witness
        endpoint = 'https://test-parent.example.test'
        parent = SimpleNamespace(profile=SimpleNamespace(endpoint=endpoint, workspace_id='parent-workspace'))
        child = SimpleNamespace(profile=SimpleNamespace(endpoint='https://test-child.example.test'))
        workspace = {'workspace_id': 'parent-workspace', 'current_graph_id': 'actual-initial-graph',
                     'desired_graph_id': None}
        release = {'parent_endpoint': endpoint, 'parent_installation_id': 'test-parent',
                   'parent_workspace_id': 'parent-workspace'}
        installation = {'installation_id': 'test-parent', 'workspace_id': 'parent-workspace',
                        'external_endpoint': endpoint}
        plan = {'digest': 'root-plan-digest', 'input': {'installation': installation}}
        receipt = {'phase': 'complete', 'pending': None, 'plan_digest': 'root-plan-digest',
            'labels': {'org.openj92.cpk.installation': 'test-parent'},
            'observations': {'public_setup': {'commands': [{
                'route': 'command.workspace.create', 'workspace_id': 'parent-workspace',
                'current_graph_id': 'actual-initial-graph'}]}}}
        graph = GraphDescriptorCodec().encode(DeploymentGraph('parent-workspace'))
        current = {'graph_id': 'actual-initial-graph', 'assigned': True, 'graph_descriptor': graph}
        events = []
        def read(client, route):
            self.assertIs(client, parent)
            events.append(route)
            return {'workspace': workspace} if route == 'read.workspace' else current
        def denial(client, state):
            self.assertIs(client, parent)
            events.append('wrong-credential-denial')
            return {'denied': True, 'endpoint': endpoint}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'state').mkdir()
            for path, value in ((root / 'release.json', release), (root / 'plan.json', plan),
                                (root / 'state' / 'receipt.json', receipt)):
                path.write_text(json.dumps(value))
            with patch.object(witness, 'ROOT', root), patch.object(witness, 'read', side_effect=read), \
                    patch.object(witness, 'verify_denial', side_effect=denial), \
                    patch.object(witness, 'PublicHttpTransport', return_value=SimpleNamespace(
                        call=lambda route, **kwargs: read(parent, route))):
                parent.profile.endpoint = 'https://another-root.example.test'
                with self.assertRaises(AssertionError):
                    witness.verify_parent_fixture(parent, child, root)
                self.assertEqual(events, [])
                parent.profile.endpoint = endpoint
                workspace['current_graph_id'] = 'another-root-graph'
                with self.assertRaises(AssertionError):
                    witness.verify_parent_fixture(parent, child, root)
                self.assertEqual(events, ['read.workspace'])
                workspace['current_graph_id'] = 'actual-initial-graph'
                events.clear()
                result = witness.verify_parent_fixture(parent, child, root)
                self.assertTrue(result['authenticated'])
                self.assertTrue(result['wrong_credential']['denied'])
                self.assertEqual(events, ['read.workspace', 'read.current-graph', 'wrong-credential-denial'])

    def test_fixture_prepares_valid_shared_child_and_separate_workspace_material(self):
        from products.cpk_server.tests import live_child_fixture as fixture
        from control_plane_kit_servers_cpk_server.bootstrap import plan_root_bootstrap
        release = {'parent_installation_id': 'test-parent', 'parent_workspace_id': 'parent-workspace',
            'child_installation_id': 'test-child', 'child_workspace_id': 'child-workspace',
            'loopback_port': 18089, 'hostname': 'test-child.example.test',
            'gateway_hostname': 'test-run-gateway.example.test',
            'parent_endpoint': 'https://test-parent.example.test',
            'parent_ingress_connection': {'tunnel_id': '11111111-1111-4111-8111-111111111111',
                'dns_record_id': 'd' * 32, 'token_reference': 'secret://bootstrap/retained-ingress/token',
                'token_sha256': sha256(b'private-parent-tunnel-token').hexdigest(),
                'configuration_sha256': sha256(json.dumps({'config': {'ingress': [
                    {'hostname': 'test-parent.example.test', 'service': 'http://cpk-bootstrap-origin:8080', 'originRequest': {}},
                    {'service': 'http_status:404'}]}}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()},
            'account_id': 'a' * 32, 'zone_id': 'b' * 32, 'zone_name': 'example.test'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[3]
            (root / 'inputs').mkdir(mode=0o700)
            (root / 'inputs' / 'parent-tunnel-token').write_bytes(b'private-parent-tunnel-token')
            (root / 'inputs' / 'parent-tunnel-token').chmod(0o400)
            original_umask = os.umask(0o077)
            try:
                with patch.object(fixture, 'ROOT', root), patch.object(fixture.live_root_bootstrap, 'ROOT', root):
                    prepared = fixture.prepare(release, source=source)
            finally:
                os.umask(original_umask)
            child = json.loads((root / 'child-input.json').read_bytes())
            document = child_installation_document(fixture.installation_from_input(child['installation']),
                                                    child_workspace_id='child-workspace')
            self.assertEqual(document['parent_workspace_id'], 'parent-workspace')
            self.assertEqual(document['child_endpoint'], 'https://test-child.example.test')
            self.assertEqual(prepared['installation']['external_endpoint'], release['parent_endpoint'])
            self.assertEqual(set(document['graph']['nodes']), {
                'test-child-cpk', 'test-child-postgres', 'test-child-secrets', 'test-child-connector'})
            graph = GraphDescriptorCodec().decode(document['graph'])
            access = fixture.installation_from_input(child['installation']).runtime_access
            for node_id, node in graph.nodes.items():
                self.assertEqual(node.runtime_authority_deliveries,
                                 (access,) if node_id == 'test-child-cpk' else ())
            root_grant = prepared['installation']['workspace_grants'][0]
            child_grant = child['installation']['workspace_grants'][0]
            self.assertEqual((root_grant['workspace_id'], child_grant['workspace_id']),
                             ('parent-workspace', 'child-workspace'))
            self.assertIn('ingress-authority:use', root_grant['scopes'])
            self.assertEqual(child_grant['scopes'], fixture.APPLICATION_SETUP_SCOPES)
            # Each independently deployed process gets its own principal document,
            # with separate role credentials and only its exact workspace grants.
            seen_credentials = set()
            from control_plane_kit_servers_cpk_server import server
            from control_plane_kit_core.identity import IdentityContractError
            from control_plane_kit_operations.cpk_server import CpkServerApplicationError, _ROUTE_AUTHORIZATION_POLICIES
            from control_plane_kit_operations.secret_providers import (
                AuthorizeSecretUse, SecretProviderAuthorizationDenied, SecretUseAuthorizationService,
            )
            from control_plane_kit_core.policies import PolicyScope
            from control_plane_kit_core.secrets import SecretReference, SecretUseIntent
            for input_value, material, workspace in (
                (prepared['installation'], root / 'material', 'parent-workspace'),
                (child['installation'], root / 'child-material', 'child-workspace'),
            ):
                self.assertEqual(input_value['control_auth']['kind'], 'multi-principal')
                self.assertNotEqual(input_value['control_auth']['principals_document'],
                                    input_value['references']['control_credential'])
                principals = json.loads((material / 'principals').read_bytes())
                verifier = server.StaticDevelopmentMultiCredentialVerifier(
                    server._static_principals((material / 'principals').read_text()))
                actors = {}
                for role in ('operator', 'approver', 'worker'):
                    filename = 'control_credential' if role == 'operator' else f'{role}_credential'
                    actors[role] = verifier.authenticate((material / filename).read_bytes())
                    with self.assertRaises(IdentityContractError):
                        actors[role].command_context('unrelated-workspace')
                _ROUTE_AUTHORIZATION_POLICIES['command.run.claim'].authorize(actors['worker'].command_context(workspace))
                _ROUTE_AUTHORIZATION_POLICIES['command.approval.decide'].authorize(actors['approver'].command_context(workspace))
                _ROUTE_AUTHORIZATION_POLICIES['command.deployment.admit'].authorize(actors['operator'].command_context(workspace))
                with self.assertRaises(CpkServerApplicationError):
                    _ROUTE_AUTHORIZATION_POLICIES['command.run.claim'].authorize(actors['operator'].command_context(workspace))
                with self.assertRaises(CpkServerApplicationError):
                    _ROUTE_AUTHORIZATION_POLICIES['command.approval.decide'].authorize(actors['worker'].command_context(workspace))
                if workspace in {'parent-workspace', 'child-workspace'}:
                    # Scope admission only: later durable reference/provider
                    # authorization and secret resolution are not exercised.
                    class StoreBoundaryReached(Exception):
                        pass
                    store_entries = []
                    def store_boundary():
                        store_entries.append(workspace)
                        raise StoreBoundaryReached()
                    secret_use = AuthorizeSecretUse(workspace_id=workspace,
                        reference=SecretReference(child['installation']['references']['postgres_password']),
                        intent=SecretUseIntent.POSTGRES_PASSWORD, actor_subject=f'{workspace}-worker',
                        correlation_id=f'{workspace}-scope-proof', requested_at='2026-09-09T12:00:00Z',
                        actor_scopes=actors['worker'].command_context(workspace).granted_scopes)
                    authorizer = SecretUseAuthorizationService(store_boundary)
                    with self.assertRaises(SecretProviderAuthorizationDenied):
                        authorizer.authorize_resolution(replace(secret_use,
                            actor_scopes=(PolicyScope.EXECUTION_OPERATE,)))
                    self.assertEqual(store_entries, [])
                    with self.assertRaises(StoreBoundaryReached):
                        authorizer.authorize_resolution(secret_use)
                    self.assertEqual(store_entries, [workspace])
                count = 4 if workspace == 'child-workspace' else 3
                self.assertEqual(len(principals), count)
                credentials = {entry['credential'] for entry in principals}
                self.assertEqual(len(credentials), count)
                self.assertTrue(seen_credentials.isdisjoint(credentials))
                seen_credentials.update(credentials)
                self.assertEqual(principals[0]['credential'], (material / 'control_credential').read_text())
                self.assertEqual([entry['kind'] for entry in principals],
                                 ['operator', 'operator', 'worker'] + (['operator'] if count == 4 else []))
                for entry in principals:
                    self.assertEqual(set(entry['workspace_grants']), {workspace})
                    self.assertNotIn(entry['credential'], json.dumps(document['graph']))
                self.assertEqual((material / 'principals').stat().st_mode & 0o777, 0o400)
                self.assertEqual(principals[2]['workspace_grants'][workspace],
                                 ['execution:operate', 'secret-provider:use'])
                self.assertNotIn('plan:approve', principals[0]['workspace_grants'][workspace])
                if count == 4:
                    probe = verifier.authenticate((material / 'probe_credential').read_bytes())
                    self.assertEqual(principals[3]['workspace_grants'][workspace], fixture.PROBE_SCOPES)
                    policy = _ROUTE_AUTHORIZATION_POLICIES['command.gateway-probe.request']
                    policy.authorize(probe.command_context(workspace))
                    with self.assertRaises(CpkServerApplicationError):
                        policy.authorize(actors['operator'].command_context(workspace))
                    for route in ('command.deployment.admit', 'command.approval.decide', 'command.run.claim'):
                        with self.assertRaises(CpkServerApplicationError):
                            _ROUTE_AUTHORIZATION_POLICIES[route].authorize(probe.command_context(workspace))
                    initializer = (material / 'initial_custody_credential').read_text()
                    self.assertNotIn(initializer, credentials)
                    self.assertNotEqual(initializer, (material / 'provider_client_credential').read_text())
                    provider_roles = json.loads((material / 'provider_credentials_document').read_bytes())
                    self.assertEqual(provider_roles[1]['grants'], [{'action': 'secret.write',
                        'workspace_id': workspace, 'intents': ['gateway.probe-signing-key', 'cloudflare.api-token']}])
                    self.assertEqual([grant for grant in provider_roles[0]['grants'] if grant['action'] == 'secret.write'],
                        [{'action': 'secret.write', 'workspace_id': workspace, 'intents': ['cloudflare.tunnel-token']}])
                    self.assertNotIn(initializer, json.dumps(child))
                    self.assertNotIn((material / 'gateway_signing_key').read_text(), json.dumps(child))
            self.assertIn({'reference': child['installation']['control_auth']['principals_document'],
                           'allowed_intents': ['application.control-token']}, prepared['setup']['secret_references'])
            for name, intent in fixture.MATERIAL_INTENTS.items():
                self.assertIn({'reference': child['installation']['references'][name], 'allowed_intents': [intent]},
                              prepared['setup']['secret_references'])
                self.assertEqual((root / 'child-material' / name).stat().st_mode & 0o777, 0o400)
            self.assertFalse((root / 'initial-custody').exists())
            self.assertFalse((root / 'child-api').exists())
            # Validate the emitted root input at its next real owner boundary,
            # including the exact-host authority and retained connection.
            root_plan = plan_root_bootstrap(json.loads((root / 'input.json').read_bytes()),
                                            driver_image_id='sha256:' + '1' * 64)
            self.assertEqual(root_plan['input'], prepared)
            for reference in (prepared['installation']['control_auth']['principals_document'],
                              prepared['installation']['references']['control_credential']):
                self.assertIn(reference, root_plan['required_material'])
                material_index = json.loads((root / 'material' / 'index.json').read_bytes())
                self.assertIn(reference, material_index['files'])
            self.assertEqual(root_plan['input']['setup']['ingress_authorities'][0]
                             ['authority']['allowed_hostname_pattern'], release['hostname'])
            self.assertEqual(root_plan['external_ingress_connection']['endpoint'], release['parent_endpoint'])
            # The accepted Secrets API returns workspace/secret identity inside
            # metadata. Wrong-target success retains pending/returned version,
            # never earns seed-complete or a second request.
            (root / 'plan.json').write_text(json.dumps(root_plan))
            (root / 'state' / 'receipt.json').write_text(json.dumps({'phase': 'complete',
                'pending': None, 'labels': {'org.openj92.cpk.installation': 'test-parent'}}))
            response = {'outcome': 'stored', 'metadata': {'workspace_id': 'wrong-workspace',
                'secret_id': 'wrong-secret', 'version_id': 'returned-version', 'version_number': 1,
                'status': 'active', 'labels': {'intent': 'application.control-token'}}}
            opener = SimpleNamespace(open=lambda *args, **kwargs: nullcontext(SimpleNamespace(
                status=200, read=lambda size: json.dumps(response).encode())))
            with patch.object(fixture, 'ROOT', root), patch.object(fixture, 'build_opener', return_value=opener):
                with self.assertRaises(AssertionError):
                    fixture.seed(release)
            progress = json.loads((root / 'initial-custody' / 'record.json').read_bytes())
            self.assertEqual(progress['phase'], 'seeding')
            self.assertIsNotNone(progress['pending'])
            self.assertEqual([item['version_id'] for item in progress['versions']], ['returned-version'])
            self.assertFalse((root / 'config').exists())

    def test_initialization_requires_exact_prepared_graph_not_matching_node_names(self):
        law = composition.ChildInstallationClientTests()
        installation = law.installation()
        expected = child_installation_document(installation, child_workspace_id='child-workspace')['graph']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = composition.RecordingClient(root, 'parent-workspace', 'http://127.0.0.1:18080')
            child = composition.RecordingClient(root, 'child-workspace', 'https://child-a.example.test')
            prepared = ClientResult('planned', '11111111-1111-4111-8111-111111111111',
                                    'parent-workspace', plan_id='plan-1')
            tracking = {'plan_id': 'plan-1', 'current_graph_id': 'graph-1',
                        'current_realized_projection_id': 'projection-1'}
            invocation = {'desired': {'sha256': ''}, 'target': {
                'workspace_id': parent.profile.workspace_id, 'endpoint_sha256': parent.profile.target_digest},
                'coordinates': {'plan_id': 'plan-1', 'desired_graph_id': 'graph-1',
                                'desired_realized_projection_id': 'projection-1'}}
            parent.journal = SimpleNamespace(read=lambda operation: invocation)
            altered = json.loads(json.dumps(expected))
            altered['public_ingresses'][0]['hostname'] = 'other.example.test'
            self.assertEqual(set(altered['nodes']), set(expected['nodes']))
            def digest(graph):
                return sha256(json.dumps(graph, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
            with patch.object(recipe, 'parent_tracking', return_value=tracking):
                invocation['desired']['sha256'] = digest(altered)
                with self.assertRaises(ChildInstallationHold):
                    recipe.initialize_after_parent(installation, parent=parent, prepared=prepared,
                        child=child, setup=law.setup(), state_directory=root / 'child-setup')
                self.assertEqual(child.calls, [])
                self.assertFalse((root / 'child-setup').exists())
                invocation['desired']['sha256'] = digest(expected)
                initialized = recipe.initialize_after_parent(installation, parent=parent, prepared=prepared,
                    child=child, setup=law.setup(), state_directory=root / 'child-setup')
                self.assertEqual(initialized['child']['status'], 'child-initialized')

    def test_empty_revision_is_saved_selected_and_verified_before_saved_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = composition.RecordingClient(root, 'parent-workspace', 'http://127.0.0.1:18080')
            events = []
            revision = {'draft_id': 'empty-draft', 'revision': 1, 'graph_id': 'empty-graph'}
            empty = GraphDescriptorCodec().encode(DeploymentGraph('parent-workspace'))
            latest = dict(revision)
            def result():
                return SimpleNamespace(descriptor=lambda: {'status': 'recorded',
                    'workspace_id': 'parent-workspace', 'revision': dict(revision)})
            def save(path, *, title):
                self.assertEqual(json.loads(path.read_bytes()), empty)
                events.append('save')
                return result()
            def select(draft_id, number):
                self.assertEqual((draft_id, number), ('empty-draft', 1))
                events.append('select')
                return result()
            def read(route, **arguments):
                events.append(route)
                if route == 'read.desired-topology-draft-revision':
                    return {'workspace_id': 'parent-workspace', **revision, 'graph_descriptor': empty}
                if route == 'read.desired-graph':
                    return {'graph_id': 'empty-graph', 'graph_descriptor': empty}
                if route == 'read.operator-overview':
                    return {'graphs': {'desired': {'draft': {'state': 'selected',
                        'selected': dict(revision), 'head': dict(latest)}}}}
                raise AssertionError('unexpected read')
            def plan(source, *, title):
                self.assertEqual(source, SavedDesiredRevision('empty-draft', 1))
                events.append('plan-saved')
                return 'prepared'
            client.draft_save, client.draft_select, client.plan = save, select, plan
            client.transport = SimpleNamespace(call=read)
            value = recipe.prepare_saved_empty(client, graph_path=root / 'empty.json')
            self.assertEqual(value, {'revision': revision, 'prepared': 'prepared'})
            self.assertEqual(events, ['save', 'select', 'read.desired-topology-draft-revision',
                                     'read.desired-graph', 'read.operator-overview', 'plan-saved'])
            events.clear()
            latest['revision'] = 2
            with self.assertRaises(ChildInstallationHold):
                recipe.prepare_saved_empty(client, graph_path=root / 'stale-empty.json')
            self.assertNotIn('plan-saved', events)
