"""Explicitly released complete-child API witness; no Docker/SQL/provider client.

A separately approved owning fixture supplies initial custody, profiles,
canonical input, restart and final retained/root cleanup. The maintained harness
orders installation, custody, application, probe and the two teardown phases;
failed/incomplete phases cannot be blindly restarted.
The test controller approves only the exact plans returned for these declared
operations. Invoking this witness requires the concrete one-run effect release.
"""

from collections import Counter
from datetime import datetime, timezone
import json
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile
from time import monotonic, sleep
from uuid import uuid4

from control_plane_kit_core.delegation_authority import DelegationAuthorityBinding
from control_plane_kit_core.gateway_delegation import GatewayProbeCommandKind, GatewayProbeRequest
from control_plane_kit_core.runtime_effects import GatewayTargetId
from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.planning import activity_operation_descriptor, compile_activity_plan
from control_plane_kit_core.products import ProductDescriptorCodec, ProductReference
from control_plane_kit_core.public_ingress import NamedPublicIngressCodec
from control_plane_kit_core.runtime_authority import RuntimeAuthorityAccessDeliveryCodec, RuntimeAuthorityReference
from control_plane_kit_core.secrets import SecretProviderEndpointReference, SecretReference
from control_plane_kit_core.topology import DeploymentGraph, GraphDescriptorCodec, diff_graphs, validate_graph
from control_plane_kit_servers_cpk_server.installation import ControlAuthCodec, DockerCpkInstallation
from control_plane_kit_servers_cpk_server.client import (
    ClientAuthorizationError, ClientProfile, ClientTransportError,
    PublicHttpTransport, TopologyClient, load_profile,
)
from control_plane_kit_servers_cpk_server.client.installation import child_installation_document, prepare_child_installation
from products.cpk_server.examples.public_child_api import (
    child_application_graph, initialize_after_parent, parent_tracking,
    prepare_saved_empty, verify_empty_convergence,
    verify_gateway_probe_response,
)


ROOT = Path('/witness')


def installation_from_input(value):
    products = {name: ProductDescriptorCodec().decode_document(document)
                for name, document in value['products'].items()}
    return DockerCpkInstallation(
        control_auth=ControlAuthCodec().decode(value.get('control_auth', {'kind': 'single-operator'})),
        installation_id=value['installation_id'], workspace_id=value['workspace_id'],
        runtime_authority=RuntimeAuthorityReference(value['runtime_authority']),
        runtime_access=RuntimeAuthorityAccessDeliveryCodec().decode(value['runtime_access']),
        cpk_product=products['cpk'], postgres_product=products['postgres'], secrets_product=products['secrets'],
        connector_product=products['connector'], ingress=NamedPublicIngressCodec().decode(value['ingress']),
        workspace_grants=tuple(WorkspaceGrant(grant['workspace_id'], tuple(PolicyScope(scope) for scope in grant['scopes']))
                               for grant in value['workspace_grants']),
        provider_endpoint_ref=SecretProviderEndpointReference(value['provider_endpoint_ref']),
        **{name: SecretReference(reference) for name, reference in value['references'].items()})


def save(state, value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert len(raw) <= 1_048_576, 'API witness record bound'
    temporary = state / 'record.new'
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, state / 'record.json')
    directory = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def read(client, route, **coordinates):
    return client.transport.call(route, path_parameters={
        'workspace_id': client.profile.workspace_id, **coordinates}, payload={}, credential_role='operator')


def read_items(client, route):
    value = client.transport.call(route, path_parameters={'workspace_id': client.profile.workspace_id},
        payload={'limit': 100}, credential_role='operator')
    assert value['workspace_id'] == client.profile.workspace_id
    assert isinstance(value['items'], list) and len(value['items']) <= 100 and value['next_cursor'] is None
    return value['items']


def application_graph(installation, workspace):
    application = json.loads((ROOT / 'child-input.json').read_bytes())['application']
    products = {name: ProductDescriptorCodec().decode_document(value).product
                for name, value in application['products'].items()}
    return child_application_graph(installation, workspace,
        hello_product=products['hello'], router_product=products['router'], gateway_product=products['gateway'],
        connector_product=products['connector'], ingress=NamedPublicIngressCodec().decode(application['ingress']),
        delegation_authority=DelegationAuthorityBinding.from_descriptor(application['delegation']))


def admit_application(client, installation, state, record, application):
    """Existing public admissions; finite phase, never automatic replay."""
    stamp = datetime.now(timezone.utc).isoformat()
    release = json.loads((ROOT / 'release.json').read_bytes())
    workspace = client.profile.workspace_id
    ingress = NamedPublicIngressCodec().decode(application['ingress'])
    registration = record['initialized']['child']['provider_registration_id']
    provider = read(client, 'read.secret-provider-detail', provider_id='control-plane-kit')
    assert provider['workspace_id'] == workspace and provider['secret_provider']['registration_id'] == registration
    authority = {'provider_kind': 'cloudflare', 'account_id': release['account_id'], 'zone_id': release['zone_id'],
        'zone_name': release['zone_name'], 'api_token_ref': application['api_token_reference'],
        'allowed_hostname_pattern': release['gateway_hostname'],
        'generated_secret_provider_registration_id': registration,
        'generated_secret_reference_prefix': application['generated_prefix']}
    issuer, key_id = application['delegation']['issuer'], application['key_id']
    products = tuple(application['products'][name] for name in ('hello', 'router', 'gateway', 'connector'))
    calls = tuple(('command.product.import', {}, {'descriptor_document': document, 'imported_at': stamp})
                  for document in products) + (
        ('command.ingress-authority.register', {}, {'authority_ref': ingress.authority_ref.reference_id,
            'authority': authority, 'admitted_at': stamp}),
        ('command.delegation-key.register', {}, {'purpose': 'gateway-probe', 'issuer': issuer,
            'key_id': key_id, 'algorithm': 'ed25519', 'public_key_pem': application['public_key_pem'],
            'private_key_reference': application['signing_key_reference'], 'admitted_at': stamp}),
        ('command.delegation-key.activate', {'issuer': issuer, 'key_id': key_id},
            {'purpose': 'gateway-probe', 'issuer': issuer, 'key_id': key_id, 'activated_at': stamp}),
    )
    record['application_admissions'] = []
    for route, path, payload in calls:
        record['pending'] = {'route': route, 'idempotency_key': str(uuid4())}
        if route == 'command.product.import':
            expected_product = ProductReference.from_document(
                ProductDescriptorCodec().decode_document(payload['descriptor_document'])).descriptor()
            record['pending']['product_reference'] = expected_product
        save(state, record)
        response = client.transport.call(route, path_parameters={'workspace_id': workspace, **path},
            payload={**payload, 'idempotency_key': record['pending']['idempotency_key']}, credential_role='operator')
        coordinates = {key: response[key] for key in ('workspace_id', 'registration_id', 'key_id', 'status')
                       if isinstance(response.get(key), str) and 0 < len(response[key]) <= 256}
        record['application_admissions'].append({'route': route, 'coordinates': coordinates})
        save(state, record)
        assert response.get('workspace_id') == workspace
        if route == 'command.product.import':
            assert response.get('status') == 'active' and coordinates.get('registration_id')
            assert response.get('reference') == expected_product
            record['application_admissions'][-1]['product_reference'] = expected_product
        elif route == 'command.ingress-authority.register':
            detail = read(client, 'read.ingress-authority-detail', authority_ref=ingress.authority_ref.reference_id)
            assert detail['workspace_id'] == workspace
            assert detail['ingress_authority']['registration_id'] == response['registration_id']
        else:
            assert response.get('key_id') == key_id and response.get('issuer') == issuer
            assert response.get('private_key_reference') == application['signing_key_reference']
        record['pending'] = None
        save(state, record)
    keys = [value for value in read_items(client, 'read.delegation-keys')
            if value.get('purpose') == 'gateway-probe' and value.get('issuer') == issuer and value.get('key_id') == key_id]
    assert len(keys) == 1
    expected = {'workspace_id': workspace, 'status': 'active', 'algorithm': 'ed25519',
                'registration_id': record['application_admissions'][-1]['coordinates']['registration_id'],
                'fingerprint_sha256': sha256((application['public_key_pem'].strip() + '\n').encode('ascii')).hexdigest()}
    assert all(keys[0].get(key) == value for key, value in expected.items())
    record['active_application_key'] = {'issuer': issuer, 'key_id': key_id,
                                       'fingerprint_sha256': expected['fingerprint_sha256']}
    save(state, record)


def verify_application_response(child, graph, current, run_id):
    router = next(node for node in graph.nodes.values() if node.node_id.endswith('-router'))
    check = next(value for value in router.block_spec.verification.checks if value.check_id == 'root-response')
    matches = []
    for item in read_items(child, 'read.observed-state'):
        evidence = item.get('payload', {}).get('http_verification', {})
        if (item.get('workspace_id') == child.profile.workspace_id
                and item.get('graph_id') == current['graph_id'] and item.get('status') == 'verified'
                and item.get('freshness') == 'fresh' and evidence.get('node_id') == router.node_id
                and evidence.get('run_id') == run_id and evidence.get('check_id') == check.check_id
                and evidence.get('provider_socket') == check.provider_socket
                and evidence.get('path') == '/' and evidence.get('http_status') in check.expected_statuses
                and evidence.get('expected_body_sha256') == check.expected_body_sha256
                and evidence.get('body_sha256_matches') is True
                and type(evidence.get('response_bytes')) is int
                and 0 < evidence['response_bytes'] <= check.policy.maximum_evidence_bytes):
            matches.append({'observation_id': item['observation_id'], 'graph_id': item['graph_id'], 'run_id': run_id,
                            'node_id': router.node_id, 'check_id': check.check_id, 'expected_body_sha256': check.expected_body_sha256})
    assert len(matches) == 1, 'current application response evidence unavailable or ambiguous'
    return matches[0]


def apply_reviewed(client, planned, *, destructive, fixture_graph):
    assert planned.status == 'planned' and planned.plan_id and planned.changes, 'expected non-noop public plan'
    assert planned.destructive is destructive, 'plan destructive classification differs from released action'
    # The existing Core owner derives the exact operations for this fixture's
    # empty <-> graph transition. Do not invent another planner or approve only
    # the lossy ClientResult target projection (which omits ingress_id).
    empty = DeploymentGraph(fixture_graph.name)
    before, after = (fixture_graph, empty) if destructive else (empty, fixture_graph)
    expected = compile_activity_plan(diff_graphs(validate_graph(before), validate_graph(after)))
    detail = read(client, 'read.plan-detail', plan_id=planned.plan_id)['plan']
    assert detail['plan_id'] == planned.plan_id, 'released plan identity differs'
    def operation_key(operation):
        return json.dumps(operation, sort_keys=True, separators=(',', ':'), allow_nan=False)
    permitted = Counter(operation_key(activity_operation_descriptor(activity.operation))
                        for activity in expected.activities)
    observed = Counter(operation_key(activity['operation']) for activity in detail['payload']['activities'])
    assert permitted and observed == permitted, 'generated actions or targets differ from released fixture transition'
    arguments = {'execute_plan': planned.plan_id,
                 'approve_destructive_plan' if destructive else 'approve_plan': planned.plan_id}
    completed = client.apply(planned.operation_ref, **arguments)
    assert (completed.status, completed.execution, completed.advancement) == ('converged', 'succeeded', 'advanced')
    return completed


def verify_denial(child, state):
    # Exercise the same real HTTPS route with a separate invalid private token.
    # Connection/TLS failures are not authorization-denial evidence.
    with tempfile.TemporaryDirectory(dir=state) as directory:
        path = Path(directory) / 'invalid-credential'
        path.write_text('deliberately-invalid-child-witness-token', encoding='ascii')
        path.chmod(0o400)
        profile = ClientProfile(child.profile.endpoint, child.profile.workspace_id,
            {role: path for role in ('operator', 'approver', 'worker')}, Path(directory))
        try:
            PublicHttpTransport(profile).call('read.workspace',
                path_parameters={'workspace_id': profile.workspace_id}, payload={}, credential_role='operator')
        except ClientAuthorizationError:
            return {'endpoint': profile.endpoint, 'workspace_id': profile.workspace_id, 'denied': True}
        raise AssertionError('wrong child credential accepted')


def parent_workspace_ready(parent):
    """Bounded read-only HTTPS readiness; authorization denial is terminal."""
    transport = PublicHttpTransport(parent.profile, timeout_seconds=1)
    deadline = monotonic() + 30
    while True:
        try:
            ready = transport.call('read.workspace',
                path_parameters={'workspace_id': parent.profile.workspace_id},
                payload={}, credential_role='operator')
            assert ready['workspace']['workspace_id'] == parent.profile.workspace_id
            return ready
        except ClientAuthorizationError:
            raise
        except ClientTransportError:
            if monotonic() >= deadline:
                raise
            sleep(0.25)


def verify_parent_fixture(parent, child, state):
    """Read-only proof of the supplied endpoint's exact disposable root."""
    release = json.loads((ROOT / 'release.json').read_bytes())
    plan = json.loads((ROOT / 'plan.json').read_bytes())
    receipt = json.loads((ROOT / 'state' / 'receipt.json').read_bytes())
    installation = plan['input']['installation']
    assert receipt['phase'] == 'complete' and receipt['pending'] is None
    assert receipt['plan_digest'] == plan['digest']
    assert installation['installation_id'] == release['parent_installation_id']
    assert receipt['labels']['org.openj92.cpk.installation'] == release['parent_installation_id']
    assert parent.profile.workspace_id == installation['workspace_id'] == release['parent_workspace_id']
    assert parent.profile.endpoint == installation['external_endpoint'] == release['parent_endpoint']
    assert parent.profile.endpoint.startswith('https://') and parent.profile.endpoint != child.profile.endpoint
    created = receipt['observations']['public_setup']['commands'][0]
    assert created['route'] == 'command.workspace.create'
    assert created['workspace_id'] == parent.profile.workspace_id
    observed = parent_workspace_ready(parent)['workspace']
    assert observed['workspace_id'] == created['workspace_id']
    assert observed['current_graph_id'] == created['current_graph_id']
    assert observed['desired_graph_id'] is None and created.get('desired_graph_id') is None
    current = read(parent, 'read.current-graph')
    assert current['graph_id'] == created['current_graph_id'] and current['assigned'] is True
    graph = GraphDescriptorCodec().decode(current['graph_descriptor'])
    assert not graph.nodes and not graph.runtimes and not graph.public_ingresses
    denied = verify_denial(parent, state)
    return {'endpoint': parent.profile.endpoint, 'workspace_id': parent.profile.workspace_id,
            'current_graph_id': current['graph_id'], 'root_plan_digest': plan['digest'],
            'authenticated': True, 'wrong_credential': denied}


def deploy(installation, parent, child, setup, state):
    state.mkdir(mode=0o700, exist_ok=False)
    record = {'phase': 'deploying', 'parent_workspace': parent.profile.workspace_id,
              'child_workspace': child.profile.workspace_id, 'pending': None}
    save(state, record)
    record['parent_public_fixture'] = verify_parent_fixture(parent, child, state)
    save(state, record)
    prepared = prepare_child_installation(installation, parent=parent,
        child_workspace_id=child.profile.workspace_id, state_directory=state / 'prepare-parent')
    record['parent_prepared'] = prepared.descriptor()
    save(state, record)
    fixture_graph = GraphDescriptorCodec().decode(child_installation_document(
        installation, child_workspace_id=child.profile.workspace_id)['graph'])
    completed = apply_reviewed(parent, prepared, destructive=False, fixture_graph=fixture_graph)
    record['parent_deployed'] = completed.descriptor()
    save(state, record)
    initialized = initialize_after_parent(installation, parent=parent, prepared=prepared, child=child,
                                          setup=setup, state_directory=state / 'initialize-child')
    record['initialized'] = initialized
    record['denial'] = verify_denial(child, state)
    record['phase'] = 'parent-initialized'
    save(state, record)
    print('child API: parent deployment, authenticated child initialization and denial PASS')


def deploy_application(installation, parent, child, state, record):
    assert record['phase'] == 'parent-initialized' and record['pending'] is None
    custody = json.loads((ROOT / 'application-custody' / 'record.json').read_bytes())
    application = json.loads((ROOT / 'child-input.json').read_bytes())['application']
    assert custody['phase'] == 'complete' and custody['pending'] is None
    assert custody['workspace_id'] == child.profile.workspace_id
    assert custody['installation_plan_id'] == record['parent_deployed']['plan_id']
    assert {(value['reference'], value['intent']) for value in custody['versions']} == {
        (application['signing_key_reference'], 'gateway.probe-signing-key'),
        (application['api_token_reference'], 'cloudflare.api-token')}
    assert len(custody['versions']) == 2
    record['phase'] = 'application-deploying'
    save(state, record)
    admit_application(child, installation, state, record, application)
    graph = application_graph(installation, child.profile.workspace_id)
    path = state / 'child-runtime.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(GraphDescriptorCodec().encode(graph), stream, separators=(',', ':'))
    runtime = child.plan(path, title='Deploy Hello/router with delegated public gateway')
    record['child_runtime_prepared'] = runtime.descriptor()
    save(state, record)
    runtime_completed = apply_reviewed(child, runtime, destructive=False, fixture_graph=graph)
    record['child_runtime_deployed'] = runtime_completed.descriptor()
    runtime_current = read(child, 'read.current-graph')
    plan = read(child, 'read.plan-detail', plan_id=runtime_completed.plan_id)['plan']
    assert runtime_current['graph_id'] == plan['desired_graph_id']
    assert runtime_current['realized_projection_id'] == plan['desired_realized_projection_id']
    record['application_current'] = {key: runtime_current[key] for key in ('graph_id', 'realized_projection_id')}
    record['application_response'] = verify_application_response(child, graph, runtime_current, runtime_completed.run_id)
    record['parent_before_restart'] = parent_tracking(parent, record['parent_prepared']['operation_ref'])
    record['phase'] = 'deployed'
    save(state, record)
    print('child API: approved Hello/router/gateway deployment and exact body response PASS')


def reconnect(installation, parent, child, state, record):
    assert record['phase'] == 'deployed', 'reconnect requires completed deployment and explicit parent restart'
    record['phase'] = 'reconnecting'
    save(state, record)
    # Corroborating fixture evidence is required; API history alone cannot prove
    # that a process actually restarted. No provider access enters this witness.
    restart = json.loads((ROOT / 'parent-restart' / 'record.json').read_bytes())
    receipt_raw = (ROOT / 'state' / 'receipt.json').read_bytes()
    receipt = json.loads(receipt_raw)
    root_plan = json.loads((ROOT / 'plan.json').read_bytes())
    parent_node = root_plan['cpk_node_id']
    assert restart['phase'] == 'complete' and restart['receipt_sha256'] == sha256(receipt_raw).hexdigest()
    assert restart['engine_id'] == receipt['engine_id'] and restart['parent_node_id'] == parent_node
    assert set(restart['before']) == set(restart['after']) == set(receipt['resources']['containers'])
    for node, before_container in restart['before'].items():
        after_container = restart['after'][node]
        assert before_container['id'] == after_container['id'] == receipt['resources']['containers'][node]['id']
        if node == parent_node:
            assert before_container['started_at'] != after_container['started_at']
        else:
            assert before_container == after_container
    # Container Running precedes API readiness. Retry only this authenticated
    # read, within a fixed deadline; never retry a mutation or authorization denial.
    parent_workspace_ready(parent)
    before = record['parent_before_restart']
    after = parent_tracking(parent, before['operation_ref'])
    for key in ('operation_ref', 'workspace_id', 'plan_id', 'run_id', 'current_graph_id', 'current_realized_projection_id'):
        assert after[key] == before[key], 'parent durable association changed across restart'
    assert after['history'] == before['history'], 'bounded parent session/plan/run/events changed across restart'
    child_workspace = read(child, 'read.workspace')['workspace']
    assert child_workspace['workspace_id'] == child.profile.workspace_id
    child_run = record['child_runtime_deployed']
    child_status = child.status(child_run['operation_ref'])
    assert child_status.status == 'converged' and child_status.run_id == child_run['run_id']
    current = read(child, 'read.current-graph')
    assert all(current[key] == value for key, value in record['application_current'].items())
    application = json.loads((ROOT / 'child-input.json').read_bytes())['application']
    probe = TopologyClient(load_profile('child-probe', config_home=ROOT / 'config'))
    assert probe.profile.workspace_id == child.profile.workspace_id and probe.profile.endpoint == child.profile.endpoint
    request = GatewayProbeRequest(GatewayProbeCommandKind.HTTP_STATUS,
                                  GatewayTargetId(installation.installation_id + '-router.internal'), '/')
    expected = {'workspace_id': child.profile.workspace_id, 'current_graph_id': current['graph_id'],
        'gateway_node_id': installation.installation_id + '-gateway',
        'gateway_runtime_id': installation.installation_id + '-proof', 'request_id': str(uuid4()),
        'actor_id': application['probe_subject'], 'issuer': application['delegation']['issuer'], 'key_id': application['key_id']}
    record['pending'] = {'route': 'command.gateway-probe.request', 'expected': expected, 'request': request.descriptor()}
    save(state, record)
    response = probe.transport.call('command.gateway-probe.request',
        path_parameters={'workspace_id': child.profile.workspace_id, 'gateway_node_id': expected['gateway_node_id']},
        payload={'request_id': expected['request_id'], 'expected_current_graph_id': current['graph_id'],
                 **request.descriptor(), 'access_path': 'named-public-ingress'}, credential_role='operator')
    candidate = response.get('gateway_probe', {}).get('probe_id')
    if isinstance(candidate, str) and 0 < len(candidate) <= 256:
        record['gateway_probe_returned_id'] = candidate
        save(state, record)
    verified = verify_gateway_probe_response(response, expected=expected, request=request,
        not_before=datetime.fromisoformat(restart['after'][parent_node]['started_at'].replace('Z', '+00:00')),
        not_after=datetime.now(timezone.utc))
    detail = read(probe, 'read.gateway-probe-detail', probe_id=verified['probe_id'])
    assert detail['workspace_id'] == child.profile.workspace_id and detail['gateway_probe'] == response['gateway_probe']
    record['gateway_probe'] = verified
    record['pending'] = None
    record['parent_after_restart'] = after
    record['parent_restart'] = restart
    record['phase'] = 'reconnected'
    save(state, record)
    print('child API: grandparent restart/history and fresh authorized gateway HTTP status/size PASS; no fresh body-hash claim')


def teardown_application(installation, parent, child, state, record):
    assert record['phase'] == 'reconnected', 'teardown requires parent restart/history proof'
    record['phase'] = 'tearing-down'
    save(state, record)
    # Application, delegated gateway and ingress leave through the child's API.
    empty_child = prepare_saved_empty(child, graph_path=state / 'child-empty.json')
    record['child_empty_revision'] = empty_child['revision']
    record['child_empty_prepared'] = empty_child['prepared'].descriptor()
    save(state, record)
    removed_child_runtime = apply_reviewed(child, empty_child['prepared'], destructive=True,
        fixture_graph=application_graph(installation, child.profile.workspace_id))
    record['child_empty'] = verify_empty_convergence(child, removed_child_runtime.operation_ref,
                                                     revision=empty_child['revision'])
    record['phase'] = 'application-empty'
    save(state, record)


def teardown_parent(installation, parent, child, state, record):
    assert record['phase'] == 'application-empty' and record['pending'] is None
    resources = json.loads((ROOT / 'child-resources' / 'record.json').read_bytes())
    assert resources['phase'] == 'application-removed' and resources['pending'] is None
    assert resources['application_empty_plan_id'] == record['child_empty']['tracking']['plan_id']
    record['phase'] = 'parent-tearing-down'
    save(state, record)
    # Parent desired EMPTY is saved/selected/read before preparing this revision.
    empty_parent = prepare_saved_empty(parent, graph_path=state / 'parent-empty.json')
    record['parent_empty_revision'] = empty_parent['revision']
    record['parent_empty_prepared'] = empty_parent['prepared'].descriptor()
    save(state, record)
    removed = apply_reviewed(parent, empty_parent['prepared'], destructive=True,
        fixture_graph=GraphDescriptorCodec().decode(child_installation_document(
            installation, child_workspace_id=child.profile.workspace_id)['graph']))
    record['parent_empty'] = verify_empty_convergence(parent, removed.operation_ref, revision=empty_parent['revision'])
    record['phase'] = 'complete'
    save(state, record)
    print('child API: saved/selected empty revisions, approved deployment and empty convergence PASS; retained resources require accounting')


def main():
    # No raw input, credential, response body or traceback is emitted on failure.
    try:
        phase = sys.argv[1]
        assert phase in {'deploy', 'deploy-application', 'reconnect', 'teardown-application', 'teardown-parent'}
        value = json.loads((ROOT / 'child-input.json').read_bytes())
        installation = installation_from_input(value['installation'])
        parent = TopologyClient(load_profile('parent', config_home=ROOT / 'config'))
        child = TopologyClient(load_profile('child', config_home=ROOT / 'config'))
        state = ROOT / 'child-api'
        if phase == 'deploy':
            deploy(installation, parent, child, value['setup'], state)
        else:
            record = json.loads((state / 'record.json').read_bytes())
            assert record['parent_workspace'] == parent.profile.workspace_id
            assert record['child_workspace'] == child.profile.workspace_id
            {'deploy-application': deploy_application, 'reconnect': reconnect,
             'teardown-application': teardown_application, 'teardown-parent': teardown_parent}[phase](
                 installation, parent, child, state, record)
        return 0
    except Exception:
        print('child API witness HOLD; inspect private phase and public client records', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
