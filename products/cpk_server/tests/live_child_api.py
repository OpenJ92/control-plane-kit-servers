"""Explicitly released complete-child API witness; no Docker/SQL/provider client.

A separately approved owning fixture supplies initial root custody, profiles,
canonical input, parent restart and final retained/root cleanup. Invoke deploy,
reconnect, then teardown; failed/incomplete phases cannot be blindly restarted.
The test controller approves only the exact plans returned for these declared
operations. Invoking this witness requires the concrete one-run effect release.
"""

import json
from hashlib import sha256
import os
from pathlib import Path
import sys
import tempfile
from time import monotonic, sleep

from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.public_ingress import NamedPublicIngressCodec
from control_plane_kit_core.runtime_authority import RuntimeAuthorityAccessDeliveryCodec, RuntimeAuthorityReference
from control_plane_kit_core.secrets import SecretProviderEndpointReference, SecretReference
from control_plane_kit_core.topology import GraphDescriptorCodec
from control_plane_kit_servers_cpk_server.installation import DockerCpkInstallation
from control_plane_kit_servers_cpk_server.client import (
    ClientAuthorizationError, ClientProfile, ClientTransportError,
    PublicHttpTransport, TopologyClient, load_profile,
)
from control_plane_kit_servers_cpk_server.client.installation import prepare_child_installation
from products.cpk_server.examples.public_child_api import (
    child_runtime_graph, initialize_after_parent, parent_tracking,
    prepare_saved_empty, verify_empty_convergence,
)


ROOT = Path('/witness')


def installation_from_input(value):
    products = {name: ProductDescriptorCodec().decode_document(document)
                for name, document in value['products'].items()}
    return DockerCpkInstallation(
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


def apply_reviewed(client, planned, *, destructive):
    assert planned.status == 'planned' and planned.plan_id and planned.changes, 'expected non-noop public plan'
    assert planned.destructive is destructive, 'plan destructive classification differs from released action'
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


def deploy(installation, parent, child, setup, state):
    state.mkdir(mode=0o700, exist_ok=False)
    record = {'phase': 'deploying', 'parent_workspace': parent.profile.workspace_id,
              'child_workspace': child.profile.workspace_id}
    save(state, record)
    prepared = prepare_child_installation(installation, parent=parent,
        child_workspace_id=child.profile.workspace_id, state_directory=state / 'prepare-parent')
    record['parent_prepared'] = prepared.descriptor()
    save(state, record)
    completed = apply_reviewed(parent, prepared, destructive=False)
    record['parent_deployed'] = completed.descriptor()
    save(state, record)
    initialized = initialize_after_parent(installation, parent=parent, prepared=prepared, child=child,
                                          setup=setup, state_directory=state / 'initialize-child')
    record['initialized'] = initialized
    record['denial'] = verify_denial(child, state)
    save(state, record)
    graph = child_runtime_graph(installation, child.profile.workspace_id)
    path = state / 'child-runtime.json'
    with path.open('x', encoding='utf-8') as stream:
        json.dump(GraphDescriptorCodec().encode(graph), stream, separators=(',', ':'))
    runtime = child.plan(path, title='Prove explicitly granted child Docker runtime')
    assert any(change['operation'] == 'start-runtime' and change['target'].get('runtime_id') ==
               f'{installation.installation_id}-proof' for change in runtime.changes), 'runtime creation absent from plan'
    record['child_runtime_prepared'] = runtime.descriptor()
    save(state, record)
    runtime_completed = apply_reviewed(child, runtime, destructive=False)
    record['child_runtime_deployed'] = runtime_completed.descriptor()
    runtime_current = read(child, 'read.current-graph')
    assert f'{installation.installation_id}-proof' in runtime_current['graph_descriptor']['runtimes']
    record['parent_before_restart'] = parent_tracking(parent, prepared.operation_ref)
    record['phase'] = 'deployed'
    save(state, record)
    print('child API: parent deployment, authenticated child setup and approved non-noop child runtime PASS')


def reconnect(installation, parent, child, state, record):
    assert record['phase'] == 'deployed', 'reconnect requires completed deployment and explicit parent restart'
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
    transport = PublicHttpTransport(parent.profile, timeout_seconds=1)
    deadline = monotonic() + 30
    while True:
        try:
            ready = transport.call('read.workspace',
                path_parameters={'workspace_id': parent.profile.workspace_id},
                payload={}, credential_role='operator')
            assert ready['workspace']['workspace_id'] == parent.profile.workspace_id
            break
        except ClientAuthorizationError:
            raise
        except ClientTransportError:
            if monotonic() >= deadline:
                raise
            sleep(0.25)
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
    record['parent_after_restart'] = after
    record['parent_restart'] = restart
    record['phase'] = 'reconnected'
    save(state, record)
    print('child API: parent restart/reconnect durable history and child usability PASS')


def teardown(installation, parent, child, state, record):
    assert record['phase'] == 'reconnected', 'teardown requires parent restart/history proof'
    record['phase'] = 'tearing-down'
    save(state, record)
    # Child proof runtime is removed through its own saved empty API revision.
    empty_child = prepare_saved_empty(child, graph_path=state / 'child-empty.json')
    record['child_empty_revision'] = empty_child['revision']
    record['child_empty_prepared'] = empty_child['prepared'].descriptor()
    save(state, record)
    removed_child_runtime = apply_reviewed(child, empty_child['prepared'], destructive=True)
    record['child_empty'] = verify_empty_convergence(child, removed_child_runtime.operation_ref,
                                                     revision=empty_child['revision'])
    save(state, record)
    # Parent desired EMPTY is saved/selected/read before preparing this revision.
    empty_parent = prepare_saved_empty(parent, graph_path=state / 'parent-empty.json')
    record['parent_empty_revision'] = empty_parent['revision']
    record['parent_empty_prepared'] = empty_parent['prepared'].descriptor()
    save(state, record)
    removed = apply_reviewed(parent, empty_parent['prepared'], destructive=True)
    record['parent_empty'] = verify_empty_convergence(parent, removed.operation_ref, revision=empty_parent['revision'])
    record['phase'] = 'complete'
    save(state, record)
    print('child API: saved/selected empty revisions, approved deployment and empty convergence PASS; retained resources require accounting')


def main():
    # No raw input, credential, response body or traceback is emitted on failure.
    try:
        phase = sys.argv[1]
        assert phase in {'deploy', 'reconnect', 'teardown'}
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
            (reconnect if phase == 'reconnect' else teardown)(installation, parent, child, state, record)
        return 0
    except Exception:
        print('child API witness HOLD; inspect private phase and public client records', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
