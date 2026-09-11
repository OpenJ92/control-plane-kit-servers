"""Gateway acceptance composition/evidence laws, not backend state machines."""

import base64
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from control_plane_kit_core.delegation_authority import DelegationAuthorityBinding
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.gateway_delegation import GatewayProbeCommandKind, GatewayProbeRequest
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.public_ingress import IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget
from control_plane_kit_core.runtime_effects import GatewayTargetId
from control_plane_kit_core.topology import compile_topology, validate_graph
from control_plane_kit_servers_cpk_server.installation import compose_docker_cpk_installation
from control_plane_kit_servers_cpk_server.client.installation import ChildInstallationHold
from products.cpk_server.examples import public_child_api as recipe
from products.cpk_server.tests import live_child_fixture as fixture
import test_child_installation_client as composition


ROOT = Path(__file__).resolve().parents[3]


class ChildGatewayExampleTests(unittest.TestCase):
    def setUp(self):
        # This suite uses the Hello renderer as a product contract oracle.
        # Restore only its own imports so the later catalogue isolation law
        # still measures imports performed by catalogue loading itself.
        self.hello_modules = {name for name in sys.modules
                             if name == 'control_plane_kit_servers_hello_server'
                             or name.startswith('control_plane_kit_servers_hello_server.')}

    def tearDown(self):
        for name in tuple(sys.modules):
            if name not in self.hello_modules and (name == 'control_plane_kit_servers_hello_server'
                    or name.startswith('control_plane_kit_servers_hello_server.')):
                sys.modules.pop(name)

    def api(self, owner, name):
        value = getattr(owner, name, None)
        self.assertTrue(callable(value), f"missing gateway acceptance behavior: {name}")
        return value

    def products(self):
        return {name: ProductDescriptorCodec().decode_document(
            (ROOT / 'products' / name / 'product.cpk.json').read_bytes()).product
            for name in ('hello_server', 'http_active_router', 'cpk_local_gateway', 'cloudflared_connector')}

    def test_selected_signer_document_preserves_image_and_flows_through_installation(self):
        select = self.api(recipe, 'gateway_signer_product')
        installation = composition.ChildInstallationClientTests().installation()
        original = installation.cpk_product
        selected = select(original)
        self.assertEqual(selected.product.image, original.product.image)
        self.assertEqual(selected.product.identity, original.product.identity)
        self.assertEqual(selected.product.runtime_contract, replace(original.product.runtime_contract,
            public_environment=selected.product.runtime_contract.public_environment))
        before = {v.name: v.value for v in original.product.runtime_contract.public_environment}
        after = {v.name: v.value for v in selected.product.runtime_contract.public_environment}
        self.assertEqual(after, {**before, 'CPK_GATEWAY_PROBE_SIGNER': 'ed25519'})
        self.assertNotEqual(before.get('CPK_GATEWAY_PROBE_SIGNER'), 'ed25519')
        topology = compose_docker_cpk_installation(replace(installation, cpk_product=selected))
        cpk = next(v for v in topology.root.children if getattr(v, 'block_id', None) == installation.cpk_node_id)
        self.assertEqual(cpk.implementation.document.product.image, original.product.image)
        self.assertEqual({v.name: v.value for v in cpk.implementation.document.product.runtime_contract.public_environment}
                         ['CPK_GATEWAY_PROBE_SIGNER'], 'ed25519')
        self.assertTrue(validate_graph(compile_topology(topology)).valid)

    def test_application_graph_declares_gateway_target_delegation_and_owned_ingress(self):
        build = self.api(recipe, 'child_application_graph')
        from control_plane_kit_servers_hello_server.server import render_hello
        installation = composition.ChildInstallationClientTests().installation()
        prefix = installation.installation_id
        products = self.products()
        ingress = NamedPublicIngress(prefix + '-gateway-public', IngressAuthorityReference('application-cloudflare'),
            PublicIngressTarget(prefix + '-gateway', 'control'), prefix + '-gateway-connector',
            'fresh-run-gateway.example.test')
        delegation = DelegationAuthorityBinding(prefix + '-gateway', DelegationKeyPurpose.GATEWAY_PROBE,
                                                'acceptance-issuer')
        graph = build(installation, 'child-workspace', hello_product=products['hello_server'],
            router_product=products['http_active_router'], gateway_product=products['cpk_local_gateway'],
            connector_product=products['cloudflared_connector'], ingress=ingress, delegation_authority=delegation)
        self.assertTrue(validate_graph(graph).valid)
        self.assertEqual(set(graph.nodes), {prefix + suffix for suffix in ('-hello', '-router', '-gateway', '-gateway-connector')})
        self.assertEqual({(e.provider_role, e.provider_socket, e.consumer_role, e.requirement_socket)
                          for e in graph.edges.values()}, {
            (prefix + '-hello', 'internal', prefix + '-router', 'active'),
            (prefix + '-router', 'internal', prefix + '-gateway', 'target-http')})
        self.assertEqual(graph.public_ingresses, (ingress,))
        self.assertEqual(graph.delegation_authorities, (delegation,))
        router = graph.node(prefix + '-router')
        checks = router.block_spec.verification.checks
        for check in products['http_active_router'].runtime_contract.verification.checks:
            self.assertIn(check, checks)
        expected = sha256(render_hello('Hello from the child control plane', 'blue')).hexdigest()
        body = next(c for c in checks if c.check_id == 'root-response')
        self.assertEqual((body.provider_socket, body.path, body.expected_body_sha256), ('internal', '/', expected))
        # A gateway name alone cannot substitute for its exact graph binding.
        with self.assertRaises(ChildInstallationHold):
            build(installation, 'child-workspace', hello_product=products['hello_server'],
                router_product=products['http_active_router'], gateway_product=products['cpk_local_gateway'],
                connector_product=products['cloudflared_connector'],
                ingress=replace(ingress, target=PublicIngressTarget(prefix + '-hello', 'internal')),
                delegation_authority=delegation)

    def test_fresh_probe_requires_exact_new_attempt_response_and_time_bounds(self):
        verify = self.api(recipe, 'verify_gateway_probe_response')
        request = GatewayProbeRequest(GatewayProbeCommandKind.HTTP_STATUS, GatewayTargetId('router.internal'), '/')
        expected = dict(workspace_id='child-workspace', current_graph_id='app-graph', gateway_node_id='gateway',
            gateway_runtime_id='app-runtime', request_id='new-request', actor_id='probe-principal',
            issuer='acceptance-issuer', key_id='key-1')
        after = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)
        until = datetime(2026, 9, 10, 12, 1, tzinfo=timezone.utc)
        attempt = {k: v for k, v in expected.items() if k not in ('issuer', 'key_id')}
        attempt.update(probe_id='new-probe', access_path='named-public-ingress', probe_kind='http-status',
            target_id='router.internal', request_digest=request.canonical_digest().value,
            status='succeeded', result_code='probe-succeeded',
            requested_at='2026-09-10T12:00:01Z', completed_at='2026-09-10T12:00:02Z',
            grant={'issuer': 'acceptance-issuer', 'key_id': 'key-1',
                   'audience': 'gateway:child-workspace:gateway', 'jti': 'new-grant',
                   'issued_at': int(after.timestamp()) + 1, 'expires_at': int(after.timestamp()) + 61},
            evidence={'outcome': 'passed', 'target_id': 'router.internal', 'probe': 'http-status',
                      'http_status': 200, 'body_size': 123})
        response = {'gateway_probe': attempt, 'replayed': False}
        result = verify(response, expected=expected, request=request, not_before=after, not_after=until)
        self.assertEqual(result['probe_id'], 'new-probe')
        self.assertEqual(result['evidence']['body_size'], 123)
        self.assertNotIn('body_sha256', result['evidence'])
        for path, value in [
            (('replayed',), True), (('gateway_probe', 'current_graph_id'), 'old-graph'),
            (('gateway_probe', 'request_id'), 'old-request'), (('gateway_probe', 'actor_id'), 'setup-actor'),
            (('gateway_probe', 'gateway_node_id'), 'other-gateway'),
            (('gateway_probe', 'gateway_runtime_id'), 'other-runtime'),
            (('gateway_probe', 'request_digest'), 'wrong-digest'),
            (('gateway_probe', 'target_id'), 'other.internal'),
            (('gateway_probe', 'access_path'), 'runtime-private'),
            (('gateway_probe', 'status'), 'intended'),
            (('gateway_probe', 'requested_at'), '2026-09-10T11:59:59Z'),
            (('gateway_probe', 'completed_at'), '2026-09-10T12:02:00Z'),
            (('gateway_probe', 'grant', 'key_id'), 'unreviewed-key'),
            (('gateway_probe', 'evidence', 'outcome'), 'failed'),
            (('gateway_probe', 'evidence', 'http_status'), 302),
            (('gateway_probe', 'evidence', 'body_size'), True),
            (('gateway_probe', 'evidence', 'body_size'), 16_385),
        ]:
            with self.subTest(path=path, value=value):
                changed = deepcopy(response)
                target = changed
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                with self.assertRaises(ChildInstallationHold):
                    verify(changed, expected=expected, request=request, not_before=after, not_after=until)

    def test_initial_custody_response_binds_workspace_reference_intent_and_version(self):
        verify = self.api(fixture, 'verify_custody_write_response')
        reference = 'secret://control-plane-kit/child-workspace/gateway/signing-key'
        secret_id = 'cpk1_' + base64.urlsafe_b64encode(reference.encode()).rstrip(b'=').decode()
        intent = 'gateway.probe-signing-key'
        response = {'outcome': 'stored', 'metadata': {'workspace_id': 'child-workspace',
            'secret_id': secret_id, 'labels': {'intent': intent}, 'status': 'active',
            'version_id': 'returned-version', 'version_number': 1}}
        result = verify(response, workspace='child-workspace', reference=reference, intent=intent)
        self.assertEqual(result['version_id'], 'returned-version')
        for field, value in [('workspace_id', 'other-workspace'), ('secret_id', 'other-secret'),
                             ('labels', {'intent': 'cloudflare.api-token'}), ('status', 'revoked'),
                             ('version_id', ''), ('version_number', True), ('version_number', 0)]:
            with self.subTest(field=field):
                changed = deepcopy(response)
                changed['metadata'][field] = value
                with self.assertRaises(AssertionError):
                    verify(changed, workspace='child-workspace', reference=reference, intent=intent)

    def test_initial_application_custody_requires_exact_namespace_and_preserves_uncertain_write(self):
        api = {'phase': 'parent-initialized', 'pending': None, 'parent_deployed': {'plan_id': 'installation-plan'}}
        resources = {'phase': 'installation-observed', 'pending': None, 'installation_plan_id': 'installation-plan',
                     'child_workspace_id': 'child-workspace', 'child_cpk_container_id': 'a' * 64}
        release = {'child_workspace_id': 'child-workspace', 'child_installation_id': 'test-child'}
        application = {'signing_key_reference': 'secret://control-plane-kit/child-workspace/gateway/signing-key',
                       'api_token_reference': 'secret://control-plane-kit/child-workspace/gateway/cloudflare-api'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('child-api', 'child-resources', 'child-material', 'inputs'):
                (root / name).mkdir(mode=0o700)
            for name, value in (('child-api/record.json', api), ('child-resources/record.json', resources),
                                ('child-input.json', {'application': application})):
                (root / name).write_text(json.dumps(value))
            for name in ('child-material/initial_custody_credential', 'child-material/gateway_signing_key',
                         'inputs/cloudflare-token'):
                (root / name).write_text('synthetic-private-test-material')
                (root / name).chmod(0o400)
            calls = []
            def send(request, **kwargs):
                persisted = json.loads((root / 'application-custody/record.json').read_bytes())
                self.assertEqual(persisted['pending']['reference'], application['signing_key_reference'])
                self.assertEqual(persisted['namespace_container_id'], 'a' * 64)
                self.assertTrue(request.full_url.startswith('http://test-child-secrets:8081/v1/workspaces/child-workspace/'))
                calls.append(request.full_url)
                response = {'outcome': 'stored', 'metadata': {'workspace_id': 'wrong-workspace',
                    'secret_id': 'wrong-secret', 'version_id': 'returned-version', 'version_number': 1,
                    'status': 'active', 'labels': {'intent': 'gateway.probe-signing-key'}}}
                return nullcontext(SimpleNamespace(status=200, read=lambda size: json.dumps(response).encode()))
            with patch.object(fixture, 'ROOT', root), patch.object(fixture, 'build_opener',
                    return_value=SimpleNamespace(open=send)), patch.dict(os.environ, {'CPK_CHILD_NAMESPACE_ID': 'b' * 64}):
                with self.assertRaises(AssertionError):
                    fixture.seed_application_custody(release)
                self.assertEqual(calls, [])
                self.assertFalse((root / 'application-custody').exists())
                os.environ['CPK_CHILD_NAMESPACE_ID'] = 'a' * 64
                with self.assertRaises(AssertionError):
                    fixture.seed_application_custody(release)
                record = json.loads((root / 'application-custody/record.json').read_bytes())
                self.assertEqual(record['phase'], 'seeding')
                self.assertIsNotNone(record['pending'])
                self.assertEqual(record['versions'][0]['version_id'], 'returned-version')
                with self.assertRaises(FileExistsError):
                    fixture.seed_application_custody(release)
                self.assertEqual(len(calls), 1)

    def test_application_custody_and_removal_gate_dependent_public_mutation(self):
        from products.cpk_server.tests import live_child_api as witness
        child = SimpleNamespace(profile=SimpleNamespace(workspace_id='child-workspace'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'application-custody').mkdir()
            (root / 'child-resources').mkdir()
            (root / 'child-input.json').write_text(json.dumps({'application': {}}))
            (root / 'application-custody/record.json').write_text(json.dumps({'phase': 'seeding', 'pending': {}}))
            (root / 'child-resources/record.json').write_text(json.dumps({'phase': 'observed', 'pending': None}))
            with patch.object(witness, 'ROOT', root), patch.object(witness, 'admit_application') as admit, \
                    patch.object(witness, 'prepare_saved_empty') as prepare:
                with self.assertRaises(AssertionError):
                    witness.deploy_application(None, None, child, root, {'phase': 'parent-initialized', 'pending': None})
                admit.assert_not_called()
                with self.assertRaises(AssertionError):
                    witness.teardown_parent(None, None, child, root, {'phase': 'application-empty', 'pending': None})
                prepare.assert_not_called()

    def test_deployment_body_evidence_requires_current_run_target_hash_and_freshness(self):
        from products.cpk_server.tests import live_child_api as witness
        from control_plane_kit_core.verification import HttpCheck
        check = HttpCheck(check_id='root-response', provider_socket='internal', path='/', expected_body_sha256='a' * 64)
        router = SimpleNamespace(node_id='fixture-router', block_spec=SimpleNamespace(
            verification=SimpleNamespace(checks=(check,))))
        graph = SimpleNamespace(nodes={'fixture-router': router})
        child = SimpleNamespace(profile=SimpleNamespace(workspace_id='child-workspace'))
        item = {'observation_id': 'observation', 'workspace_id': 'child-workspace', 'graph_id': 'current',
            'status': 'verified', 'freshness': 'fresh', 'payload': {'http_verification': {
                'node_id': 'fixture-router', 'run_id': 'new-run', 'check_id': 'root-response',
                'provider_socket': 'internal', 'path': '/', 'http_status': 200,
                'expected_body_sha256': 'a' * 64, 'body_sha256_matches': True, 'response_bytes': 123}}}
        with patch.object(witness, 'read_items', return_value=[item]):
            result = witness.verify_application_response(child, graph, {'graph_id': 'current'}, 'new-run')
            self.assertEqual(result['expected_body_sha256'], 'a' * 64)
        for path, value in [(('workspace_id',), 'foreign'), (('graph_id',), 'old'), (('freshness',), 'stale'),
                (('payload', 'http_verification', 'run_id'), 'old-run'),
                (('payload', 'http_verification', 'provider_socket'), 'other'),
                (('payload', 'http_verification', 'expected_body_sha256'), 'b' * 64),
                (('payload', 'http_verification', 'body_sha256_matches'), False)]:
            changed = deepcopy(item)
            target = changed
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            with self.subTest(path=path), patch.object(witness, 'read_items', return_value=[changed]):
                with self.assertRaises(AssertionError):
                    witness.verify_application_response(child, graph, {'graph_id': 'current'}, 'new-run')
        with patch.object(witness, 'read_items', return_value=[item, item]):
            with self.assertRaises(AssertionError):
                witness.verify_application_response(child, graph, {'graph_id': 'current'}, 'new-run')

    def test_public_admission_imports_exact_app_products_and_uses_redacted_key_readback(self):
        from products.cpk_server.tests import live_child_api as witness
        workspace, issuer, key_id = 'child-workspace', 'acceptance-issuer', 'key-1'
        application = {'products': {name: json.loads((ROOT / 'products' / directory / 'product.cpk.json').read_bytes())
            for name, directory in (('hello', 'hello_server'), ('router', 'http_active_router'),
                                    ('gateway', 'cpk_local_gateway'), ('connector', 'cloudflared_connector'))},
            'ingress': NamedPublicIngress('gateway-public', IngressAuthorityReference('application-cloudflare'),
                PublicIngressTarget('gateway', 'control'), 'gateway-connector', 'fresh-gateway.example.test').descriptor(),
            'delegation': {'issuer': issuer}, 'key_id': key_id, 'public_key_pem': 'fixture-public-key\n',
            'signing_key_reference': 'secret://control-plane-kit/child-workspace/gateway/signing-key',
            'api_token_reference': 'secret://control-plane-kit/child-workspace/gateway/cloudflare-api',
            'generated_prefix': 'secret://control-plane-kit/child-workspace/gateway/generated'}
        public_key = {'workspace_id': workspace, 'purpose': 'gateway-probe', 'issuer': issuer, 'key_id': key_id,
            'registration_id': 'key-registration', 'algorithm': 'ed25519', 'status': 'active',
            'fingerprint_sha256': sha256(application['public_key_pem'].encode()).hexdigest()}
        self.assertNotIn('private_key_reference', public_key)  # Real public projection omits it.
        for corrupt in (False, True):
            with self.subTest(corrupt_product=corrupt), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                release = {'account_id': 'a' * 32, 'zone_id': 'b' * 32,
                           'zone_name': 'example.test', 'gateway_hostname': 'fresh-gateway.example.test'}
                (root / 'release.json').write_text(json.dumps(release))
                record = {'pending': None, 'initialized': {'child': {'provider_registration_id': 'child-provider'}}}
                commands = []
                def call(route, **arguments):
                    self.assertEqual(arguments['path_parameters']['workspace_id'], workspace)
                    if route == 'read.secret-provider-detail':
                        return {'workspace_id': workspace, 'secret_provider': {'registration_id': 'child-provider'}}
                    if route == 'read.ingress-authority-detail':
                        return {'workspace_id': workspace, 'ingress_authority': {'registration_id': 'ingress-registration'}}
                    if route == 'read.delegation-keys':
                        return {'workspace_id': workspace, 'items': [public_key], 'next_cursor': None}
                    pending = json.loads((root / 'record.json').read_bytes())['pending']
                    self.assertEqual(pending['route'], route)
                    self.assertEqual(pending['idempotency_key'], arguments['payload']['idempotency_key'])
                    commands.append(route)
                    payload = arguments['payload']
                    if route == 'command.product.import':
                        document = ProductDescriptorCodec().decode_document(payload['descriptor_document'])
                        reference = ProductReference.from_document(document).descriptor()
                        self.assertEqual(pending['product_reference'], reference)
                        return {'workspace_id': workspace, 'registration_id': 'product-registration', 'status': 'active',
                                'reference': {} if corrupt else reference}
                    if route == 'command.ingress-authority.register':
                        self.assertEqual(payload['authority']['generated_secret_provider_registration_id'], 'child-provider')
                        self.assertEqual(payload['authority']['allowed_hostname_pattern'], release['gateway_hostname'])
                        return {'workspace_id': workspace, 'registration_id': 'ingress-registration'}
                    self.assertIn(route, ('command.delegation-key.register', 'command.delegation-key.activate'))
                    return {**public_key, 'private_key_reference': application['signing_key_reference']}
                client = SimpleNamespace(profile=SimpleNamespace(workspace_id=workspace), transport=SimpleNamespace(call=call))
                with patch.object(witness, 'ROOT', root):
                    if corrupt:
                        with self.assertRaises(AssertionError):
                            witness.admit_application(client, None, root, record, application)
                        self.assertEqual(commands, ['command.product.import'])
                        self.assertIsNotNone(record['pending'])
                    else:
                        witness.admit_application(client, None, root, record, application)
                        self.assertEqual(commands, ['command.product.import'] * 4 + ['command.ingress-authority.register',
                            'command.delegation-key.register', 'command.delegation-key.activate'])
                        self.assertIsNone(record['pending'])
                        self.assertEqual(record['active_application_key']['key_id'], key_id)
