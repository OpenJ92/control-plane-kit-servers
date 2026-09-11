"""Gateway acceptance composition/evidence laws, not backend state machines."""

import base64
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sys
import unittest

from control_plane_kit_core.delegation_authority import DelegationAuthorityBinding
from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.gateway_delegation import GatewayProbeCommandKind, GatewayProbeRequest
from control_plane_kit_core.products import ProductDescriptorCodec
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
