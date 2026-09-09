"""Composition laws only; actual joined acceptance belongs to live_child_api."""

from hashlib import sha256
import json
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
