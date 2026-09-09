"""Composition laws only; actual joined acceptance belongs to live_child_api."""

from hashlib import sha256
from contextlib import nullcontext
import json
import os
from pathlib import Path
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
    def test_fixture_prepares_valid_shared_child_and_separate_workspace_material(self):
        from products.cpk_server.tests import live_child_fixture as fixture
        release = {'parent_installation_id': 'test-parent', 'parent_workspace_id': 'parent-workspace',
            'child_installation_id': 'test-child', 'child_workspace_id': 'child-workspace',
            'loopback_port': 18089, 'hostname': 'test-child.example.test',
            'account_id': 'a' * 32, 'zone_id': 'b' * 32, 'zone_name': 'example.test'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = Path(__file__).resolve().parents[3]
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
            self.assertEqual(set(document['graph']['nodes']), {
                'test-child-cpk', 'test-child-postgres', 'test-child-secrets', 'test-child-connector'})
            root_grant = prepared['installation']['workspace_grants'][0]
            child_grant = child['installation']['workspace_grants'][0]
            self.assertEqual((root_grant['workspace_id'], child_grant['workspace_id']),
                             ('parent-workspace', 'child-workspace'))
            self.assertIn('ingress-authority:use', root_grant['scopes'])
            self.assertNotIn('ingress-authority:use', child_grant['scopes'])
            for name, intent in fixture.MATERIAL_INTENTS.items():
                self.assertIn({'reference': child['installation']['references'][name], 'allowed_intents': [intent]},
                              prepared['setup']['secret_references'])
                self.assertEqual((root / 'child-material' / name).stat().st_mode & 0o777, 0o400)
            self.assertFalse((root / 'initial-custody').exists())
            self.assertFalse((root / 'child-api').exists())
            # The accepted Secrets API returns workspace/secret identity inside
            # metadata. Wrong-target success retains pending/returned version,
            # never earns seed-complete or a second request.
            (root / 'plan.json').write_text(json.dumps({'input': prepared}))
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
