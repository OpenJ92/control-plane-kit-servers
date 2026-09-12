"""One-run root fixture inputs and initial custody; never child orchestration.

Source for the separately released #163 owning fixture. No standalone command
is dispatched until the complete effect envelope and fixture integration have
been reviewed. Initial fixture writes are distinct from production generation.
"""

import base64
import json
import os
from pathlib import Path
import secrets
from urllib.parse import quote
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from control_plane_kit_core.secrets import SecretUseIntent
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.public_ingress import IngressAuthorityReference, NamedPublicIngress, PublicIngressTarget
from products.cpk_server.examples.root_bootstrap_input import example_input
from products.cpk_server.tests import live_root_bootstrap
from products.cpk_server.tests.live_child_api import installation_from_input, save
from products.cpk_server.examples.public_child_api import gateway_signer_product
from control_plane_kit_servers_cpk_server.client.installation import child_installation_document
from control_plane_kit_servers_cpk_server.bootstrap_runtime import private_read


ROOT = Path('/witness')
SCOPES = [
    'hub:instance:create', 'instance:workspace:read', 'instance:workspace:edit',
    'secret-provider:register', 'secret-provider:read', 'secret-provider:use',
    'runtime-authority:register', 'runtime-authority:read', 'runtime-authority:use',
    'runtime-authority-delivery:register', 'runtime-authority-delivery:read',
    'plan:request', 'plan:approve', 'plan:approve-destructive', 'plan:execute', 'execution:operate',
]
MATERIAL_INTENTS = {
    'control_credential': 'application.control-token',
    'postgres_password': 'postgres.password',
    'custody_root_key': 'secrets.custody-root-key',
    'provider_credentials_document': 'secrets.provider-credentials-document',
    'provider_client_credential': 'application.control-token',
}
APPLICATION_INTENTS = ['gateway.probe-signing-key', 'cloudflare.api-token', 'cloudflare.tunnel-token']
APPLICATION_SETUP_SCOPES = SCOPES + [
    'ingress-authority:register', 'ingress-authority:read', 'ingress-authority:use',
    'delegation-key:register', 'delegation-key:read', 'delegation-key:activate',
]
PROBE_SCOPES = ['instance:workspace:read', 'gateway-probe:use', 'delegation-key:use', 'secret-provider:use']


def _private(path, value):
    raw = value.encode() if isinstance(value, str) else value
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400), 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def _principal_material(directory, workspace, scopes, *, worker_secret_use=False, probe=False):
    """Separate fixture actors; the server owns their authentication policy."""
    operator = (directory / 'control_credential').read_text()
    approvals = ['plan:approve', 'plan:approve-destructive']
    principals = []
    for role, kind, grants in (
        ('operator', 'operator', [scope for scope in scopes if scope not in approvals + ['execution:operate']]),
        ('approver', 'operator', approvals),
        ('worker', 'worker', ['execution:operate'] + (['secret-provider:use'] if worker_secret_use else [])),
    ):
        credential = operator if role == 'operator' else secrets.token_urlsafe(48)
        if role != 'operator':
            _private(directory / f'{role}_credential', credential)
        principals.append({'credential': credential, 'subject_id': f'{workspace}-{role}',
                           'kind': kind, 'workspace_grants': {workspace: grants}})
    if probe:
        credential = secrets.token_urlsafe(48)
        _private(directory / 'probe_credential', credential)
        principals.append({'credential': credential, 'subject_id': f'{workspace}-probe',
                           'kind': 'operator', 'workspace_grants': {workspace: PROBE_SCOPES}})
    _private(directory / 'principals', json.dumps(principals))


def prepare(release, *, source=Path('/source')):
    """Create only new private fixture input, before root/provider effects."""
    run = release['parent_installation_id']
    workspace = release['parent_workspace_id']
    child_id = release['child_installation_id']
    child_workspace = release['child_workspace_id']
    assert run != child_id and workspace != child_workspace
    gateway_hostname = release['gateway_hostname']
    assert (isinstance(gateway_hostname, str) and gateway_hostname.endswith('.' + release['zone_name'])
            and gateway_hostname != release['hostname']), 'distinct in-zone gateway hostname required'
    endpoint = urlsplit(release['parent_endpoint'])
    assert (endpoint.scheme == 'https' and endpoint.hostname and endpoint.netloc == endpoint.hostname
            and not endpoint.path and not endpoint.query and not endpoint.fragment
            and endpoint.hostname != release['hostname']), 'distinct exact parent HTTPS endpoint required'
    assert gateway_hostname != endpoint.hostname
    root = example_input(source, installation_id=run, workspace_id=workspace, port=release['loopback_port'])
    # Operator-supplied ingress is initial infrastructure. The accepted root
    # bootstrap consumes this endpoint without provisioning its ingress.
    root['installation']['external_endpoint'] = release['parent_endpoint']
    root['external_ingress_connection'] = {**release['parent_ingress_connection'],
        'connector_product': json.loads((source / 'products/cloudflared_connector/product.cpk.json').read_bytes())}
    prefix = f'secret://control-plane-kit/{workspace}'
    child_prefix = f'{prefix}/child'
    intents = sorted(set(MATERIAL_INTENTS.values()) | {'cloudflare.api-token', 'cloudflare.tunnel-token'})
    for intent in intents:
        SecretUseIntent(intent)
    root['installation']['workspace_grants'][0]['scopes'] = SCOPES + [
        'ingress-authority:register', 'ingress-authority:read', 'ingress-authority:use']
    root['installation']['control_auth'] = {
        'kind': 'multi-principal', 'principals_document': f'{prefix}/principals'}
    root['setup']['provider'].update(allowed_reference_prefixes=[prefix], allowed_intents=intents)
    ingress_authority = f'{run}-cloudflare'
    child = {
        'installation_id': child_id, 'workspace_id': workspace,
        # The same named capability is independently registered in each workspace.
        # Root setup admits this delivery for the parent graph; child setup admits
        # its own local interpretation, rather than inheriting parent scopes.
        'runtime_authority': root['installation']['runtime_access']['authority_ref']['reference_id'],
        'runtime_access': root['installation']['runtime_access'],
        'products': {**root['installation']['products'], 'connector': json.loads(
            (source / 'products/cloudflared_connector/product.cpk.json').read_bytes())},
        'references': {name: f'{child_prefix}/{name}' for name in MATERIAL_INTENTS},
        'workspace_grants': [{'workspace_id': child_workspace, 'scopes': APPLICATION_SETUP_SCOPES}],
        'control_auth': {'kind': 'multi-principal', 'principals_document': f'{child_prefix}/principals'},
        'provider_endpoint_ref': f'{child_id}-provider',
        'ingress': NamedPublicIngress(f'{child_id}-public', IngressAuthorityReference(ingress_authority),
            PublicIngressTarget(f'{child_id}-cpk', 'http-api'), f'{child_id}-connector',
            release['hostname']).descriptor(),
    }
    selected = ProductDescriptorCodec().decode_document(child['products']['cpk'])
    child['products']['cpk'] = json.loads(gateway_signer_product(selected).content)
    child['references']['provider_bootstrap_credential_ref'] = f'secret://control-plane-kit/{child_workspace}/bootstrap'
    application_prefix = f'secret://control-plane-kit/{child_workspace}/gateway'
    application = {
        'products': {name: json.loads((source / 'products' / directory / 'product.cpk.json').read_bytes())
                     for name, directory in (('hello', 'hello_server'), ('router', 'http_active_router'),
                                             ('gateway', 'cpk_local_gateway'), ('connector', 'cloudflared_connector'))},
        'ingress': NamedPublicIngress(f'{child_id}-gateway-public', IngressAuthorityReference(f'{child_id}-gateway-cloudflare'),
            PublicIngressTarget(f'{child_id}-gateway', 'control'), f'{child_id}-gateway-connector', gateway_hostname).descriptor(),
        'delegation': {'delegate_node_id': f'{child_id}-gateway', 'purpose': 'gateway-probe',
                       'issuer': f'cpk:{child_workspace}'},
        'key_id': f'{child_id}-gateway-key', 'signing_key_reference': application_prefix + '/signing-key',
        'api_token_reference': application_prefix + '/cloudflare-api', 'generated_prefix': application_prefix + '/generated',
        'probe_subject': f'{child_workspace}-probe',
    }
    child_input = {'installation': child, 'setup': {'workspace_name': 'Child acceptance workspace',
        'provider': {'provider_id': 'control-plane-kit',
            'allowed_reference_prefixes': [f'secret://control-plane-kit/{child_workspace}'],
            'allowed_intents': ['application.control-token', *APPLICATION_INTENTS]},
        'secret_references': [
            {'reference': application['signing_key_reference'], 'allowed_intents': ['gateway.probe-signing-key']},
            {'reference': application['api_token_reference'], 'allowed_intents': ['cloudflare.api-token']},
        ]}, 'application': application}
    # Existing codecs/composer validate exact values before fixture material exists.
    child_installation_document(installation_from_input(child), child_workspace_id=child_workspace)
    root['setup']['secret_references'] = [
        {'reference': child['references'][name], 'allowed_intents': [intent]}
        for name, intent in MATERIAL_INTENTS.items()]
    root['setup']['secret_references'].append({
        'reference': child['control_auth']['principals_document'],
        'allowed_intents': ['application.control-token']})
    root['setup']['secret_references'].append({'reference': f'{prefix}/cloudflare-api',
                                              'allowed_intents': ['cloudflare.api-token']})
    root['setup']['ingress_authorities'] = [{'authority_ref': ingress_authority, 'authority': {
        'provider_kind': 'cloudflare', 'account_id': release['account_id'], 'zone_id': release['zone_id'],
        'zone_name': release['zone_name'], 'api_token_ref': f'{prefix}/cloudflare-api',
        'allowed_hostname_pattern': release['hostname'],
        # Existing bootstrap setup replaces this syntactic placeholder with the
        # actual public provider registration response before registration.
        'generated_secret_provider_registration_id': 'returned-root-provider',
        'generated_secret_reference_prefix': f'{prefix}/generated'}}]
    live_root_bootstrap.prepare(run, document=root)
    material = ROOT / 'material'
    _principal_material(material, workspace, root['installation']['workspace_grants'][0]['scopes'],
                        worker_secret_use=True)
    # Original reusable credential remains operator-owned outside this fixture.
    # Only its approved copy and protected connector volume belong to this run.
    from hashlib import sha256
    ingress_token = private_read(ROOT / 'inputs' / 'parent-tunnel-token')
    assert sha256(ingress_token).hexdigest() == release['parent_ingress_connection']['token_sha256']
    _private(material / 'parent-tunnel-token', ingress_token)
    index_path = material / 'index.json'
    index = json.loads(index_path.read_bytes())
    token_reference = release['parent_ingress_connection']['token_reference']
    assert token_reference not in index['files']
    index['files'][token_reference] = 'parent-tunnel-token'
    index['files'][root['installation']['control_auth']['principals_document']] = 'principals'
    index_path.chmod(0o600)
    index_path.write_text(json.dumps(index))
    index_path.chmod(0o400)
    token = (material / 'provider_client_credential').read_text()
    grants = [{'action': action, 'workspace_id': workspace, 'intents': intents}
              for action in ('secret.write', 'secret.resolve')]
    grants += [{'action': action, 'workspace_id': workspace} for action in ('secret.revoke', 'secret.metadata')]
    # Replace only the newly created fixture-owned input, before any bootstrap.
    credentials = material / 'provider_credentials_document'
    credentials.chmod(0o600)
    credentials.write_text(json.dumps([{'subject': 'root-child-witness', 'token': token, 'grants': grants}]))
    credentials.chmod(0o400)
    child_material = ROOT / 'child-material'
    child_material.mkdir(mode=0o700, exist_ok=False)
    child_token = secrets.token_urlsafe(48)
    initial_token = secrets.token_urlsafe(48)
    _private(child_material / 'initial_custody_credential', initial_token)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    signing_key = Ed25519PrivateKey.generate()
    _private(child_material / 'gateway_signing_key', signing_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    application['public_key_pem'] = signing_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode('ascii')
    values = {'control_credential': secrets.token_urlsafe(48),
        'postgres_password': secrets.token_urlsafe(48),
        'custody_root_key': base64.urlsafe_b64encode(os.urandom(32)).decode(),
        'provider_client_credential': child_token,
        'provider_credentials_document': json.dumps([
            {'subject': 'child-witness', 'token': child_token, 'grants': [
                {'action': 'secret.resolve', 'workspace_id': child_workspace,
                 'intents': ['application.control-token', *APPLICATION_INTENTS]},
                {'action': 'secret.write', 'workspace_id': child_workspace, 'intents': ['cloudflare.tunnel-token']},
                {'action': 'secret.metadata', 'workspace_id': child_workspace},
                {'action': 'secret.revoke', 'workspace_id': child_workspace}]},
            {'subject': 'child-initial-custody', 'token': initial_token, 'grants': [
                {'action': 'secret.write', 'workspace_id': child_workspace,
                 'intents': ['gateway.probe-signing-key', 'cloudflare.api-token']}]}])}
    for name, value in values.items():
        _private(child_material / name, value)
    _principal_material(child_material, child_workspace, APPLICATION_SETUP_SCOPES, worker_secret_use=True, probe=True)
    _private(ROOT / 'child-input.json', json.dumps(child_input))
    # Profile files are deliberately made later by the actual controller UID.
    # Do not bypass the maintained client's private-file ownership checks.
    return root


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_custody_write_response(response, *, workspace, reference, intent):
    """Validate a stored initial value; callers persist returned IDs first."""
    assert response.get('outcome') == 'stored', 'initial custody value was not stored'
    metadata = response['metadata']
    secret_id = 'cpk1_' + base64.urlsafe_b64encode(reference.encode()).rstrip(b'=').decode()
    identity, version = metadata.get('version_id'), metadata.get('version_number')
    assert isinstance(identity, str) and 0 < len(identity) <= 256 and type(version) is int and version > 0
    assert metadata.get('workspace_id') == workspace and metadata.get('secret_id') == secret_id
    assert metadata.get('status') == 'active' and metadata.get('labels', {}).get('intent') == intent
    return {'reference': reference, 'intent': intent, 'version_id': identity, 'version_number': version}


def _store_initial_values(state, record, *, workspace, base_url, token, subject, items):
    """Two finite initial-custody phases share the same supported HTTP write."""
    opener = build_opener(_NoRedirect())
    for reference, intent, path in items:
        record['pending'] = {'reference': reference, 'intent': intent}
        save(state, record)
        raw = private_read(path)
        assert 0 < len(raw) <= 65_536
        secret_id = 'cpk1_' + base64.urlsafe_b64encode(reference.encode()).rstrip(b'=').decode()
        request = Request(f'{base_url}/v1/workspaces/{quote(workspace, safe="")}/secrets/{secret_id}',
            method='POST', headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
            data=json.dumps({'value_base64': base64.b64encode(raw).decode(), 'intent': intent,
                'labels': {'intent': intent}, 'caller_subject': subject,
                'correlation_id': f'{subject}-{len(record["versions"])}'}, separators=(',', ':')).encode())
        with opener.open(request, timeout=20) as response:
            payload_raw = response.read(65_537)
            assert response.status == 200 and len(payload_raw) <= 65_536
        payload = json.loads(payload_raw)
        metadata = payload.get('metadata', {})
        identity, version = metadata.get('version_id'), metadata.get('version_number')
        assert isinstance(identity, str) and 0 < len(identity) <= 256 and type(version) is int and version > 0
        record['versions'].append({'reference': reference, 'intent': intent,
                                   'version_id': identity, 'version_number': version})
        # Keep returned coordinates and pending intent even if identity differs.
        save(state, record)
        verify_custody_write_response(payload, workspace=workspace, reference=reference, intent=intent)
        record['pending'] = None
        save(state, record)
    record['phase'] = 'complete'
    save(state, record)


def seed_application_custody(release):
    """Initial parent-local material, after installation and before app intent."""
    api = json.loads((ROOT / 'child-api' / 'record.json').read_bytes())
    resources = json.loads((ROOT / 'child-resources' / 'record.json').read_bytes())
    assert api['phase'] == 'parent-initialized' and 'child_runtime_prepared' not in api
    assert resources['phase'] == 'installation-observed' and resources['pending'] is None
    assert resources['installation_plan_id'] == api['parent_deployed']['plan_id']
    assert resources['child_workspace_id'] == release['child_workspace_id']
    assert os.environ.get('CPK_CHILD_NAMESPACE_ID') == resources['child_cpk_container_id']
    value = json.loads((ROOT / 'child-input.json').read_bytes())
    application = value['application']
    state = ROOT / 'application-custody'
    state.mkdir(mode=0o700, exist_ok=False)
    record = {'phase': 'seeding', 'workspace_id': release['child_workspace_id'], 'pending': None, 'versions': [],
              'installation_plan_id': api['parent_deployed']['plan_id'],
              'namespace_container_id': resources['child_cpk_container_id']}
    save(state, record)
    _store_initial_values(state, record, workspace=release['child_workspace_id'],
        base_url=f'http://{release["child_installation_id"]}-secrets:8081',
        token=private_read(ROOT / 'child-material' / 'initial_custody_credential').decode('ascii'),
        subject='child-initial-custody', items=(
            (application['signing_key_reference'], 'gateway.probe-signing-key', ROOT / 'child-material' / 'gateway_signing_key'),
            (application['api_token_reference'], 'cloudflare.api-token', ROOT / 'inputs' / 'cloudflare-token'),
        ))
    print('child fixture: finite initial application custody PASS; no production key-generation claim')


def seed(release):
    """Once-only initial Secrets HTTP writes before ANY child deployment."""
    state = ROOT / 'initial-custody'
    state.mkdir(mode=0o700, exist_ok=False)
    assert not (ROOT / 'child-api').exists(), 'initial fixture provisioning is closed after child deployment starts'
    root_plan = json.loads((ROOT / 'plan.json').read_bytes())
    receipt = json.loads((ROOT / 'state' / 'receipt.json').read_bytes())
    assert receipt['phase'] == 'complete' and receipt['pending'] is None
    assert root_plan['input']['installation']['workspace_id'] == release['parent_workspace_id']
    assert receipt['labels']['org.openj92.cpk.installation'] == release['parent_installation_id']
    child = json.loads((ROOT / 'child-input.json').read_bytes())['installation']
    workspace = release['parent_workspace_id']
    record = {'phase': 'seeding', 'workspace_id': workspace, 'pending': None, 'versions': []}
    save(state, record)
    items = [(child['references'][name], intent, ROOT / 'child-material' / name)
             for name, intent in MATERIAL_INTENTS.items()]
    items.append((child['control_auth']['principals_document'],
                  'application.control-token', ROOT / 'child-material' / 'principals'))
    items.append((f'secret://control-plane-kit/{workspace}/cloudflare-api',
                  'cloudflare.api-token', ROOT / 'inputs' / 'cloudflare-token'))
    _store_initial_values(state, record, workspace=workspace,
        base_url=f'http://{release["parent_installation_id"]}-secrets:8081',
        token=private_read(ROOT / 'material' / 'provider_client_credential').decode('ascii'),
        subject='root-child-witness', items=items)
    config = ROOT / 'config' / 'cpk' / 'profiles'
    config.mkdir(mode=0o700, parents=True, exist_ok=False)
    credentials = ROOT / 'client-credentials'
    credentials.mkdir(mode=0o700, exist_ok=False)
    for name, endpoint, workspace_id, material_directory in (
        ('parent', release['parent_endpoint'], workspace, ROOT / 'material'),
        ('child', f'https://{release["hostname"]}', release['child_workspace_id'], ROOT / 'child-material'),
        ('child-probe', f'https://{release["hostname"]}', release['child_workspace_id'], ROOT / 'child-material'),
    ):
        paths = {}
        for role in ('operator', 'approver', 'worker'):
            path = credentials / f'{name}-{role}'
            source = material_directory / ('probe_credential' if name == 'child-probe' else
                                           'control_credential' if role == 'operator' else f'{role}_credential')
            _private(path, source.read_bytes())
            paths[role] = str(path)
        _private(config / f'{name}.json', json.dumps({'schema': 'cpk.client-profile.v1',
            'endpoint': endpoint, 'workspace_id': workspace_id,
            'credentials': paths,
            'state_directory': str(ROOT / f'{name}-client')}))
    print('child fixture: once-only initial custody and private client profiles prepared')


def released_input(run, digest):
    """Exact private release file; an environment variable alone grants nothing."""
    from hashlib import sha256
    raw = (ROOT / 'release.json').read_bytes()
    assert len(raw) <= 65_536 and sha256(raw).hexdigest() == digest
    value = json.loads(raw)
    assert set(value) == {'schema', 'source_head', 'parent_installation_id', 'parent_workspace_id',
        'child_installation_id', 'child_workspace_id', 'loopback_port', 'account_id', 'zone_id',
        'zone_name', 'hostname', 'gateway_hostname', 'parent_endpoint', 'parent_ingress_connection', 'retained_disposition'}
    assert value['schema'] == 'cpk.child-acceptance-release.v1'
    assert value['source_head'] == os.environ['CPK_CHILD_SOURCE_HEAD']
    assert value['parent_installation_id'] == run
    assert value['retained_disposition'] in {'retain', 'delete-owned-fixture-volumes'}
    return value


def main():
    import sys
    try:
        action, run, digest = sys.argv[1:]
        release = released_input(run, digest)
        if action == 'prepare':
            prepare(release)
        elif action == 'seed':
            seed(release)
        elif action == 'seed-application-custody':
            seed_application_custody(release)
        elif action in {'preflight', 'observe', 'observe-installation', 'verify-application-empty', 'finish'}:
            from products.cpk_server.tests import live_child_resources
            getattr(live_child_resources, action.replace('-', '_'))(release)
        elif action == 'child-id':
            record = json.loads((ROOT / 'child-resources' / 'record.json').read_bytes())
            assert record['phase'] == 'installation-observed' and record['pending'] is None
            identity = record['child_cpk_container_id']
            assert len(identity) == 64 and all(c in '0123456789abcdef' for c in identity)
            print(identity)
        elif action == 'parent-id':
            receipt = json.loads((ROOT / 'state' / 'receipt.json').read_bytes())
            plan = json.loads((ROOT / 'plan.json').read_bytes())
            assert receipt['phase'] == 'complete' and receipt['pending'] is None
            assert receipt['labels']['org.openj92.cpk.installation'] == run
            identity = receipt['resources']['containers'][plan['cpk_node_id']]['id']
            assert len(identity) == 64 and all(character in '0123456789abcdef' for character in identity)
            print(identity)
        elif action == 'require-complete':
            for name in ('initial-custody', 'application-custody', 'child-api', 'child-resources'):
                record = json.loads((ROOT / name / 'record.json').read_bytes())
                assert record['phase'] == 'complete' and record.get('pending') is None
        else:
            raise AssertionError('unknown fixture phase')
        return 0
    except Exception:
        # Never emit an HTTPError/traceback, raw response or credential-bearing
        # request. The private phase record and existing API journals own detail.
        print('child fixture HOLD; inspect private phase and public API evidence', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
