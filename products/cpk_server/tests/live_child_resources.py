"""Corroborating exact-resource reads and separately released fixture cleanup.

Never deploys, repairs or removes child compute. Public API convergence must
precede the final checks. The owning one-run release permits only these bounded
reads and the explicitly chosen retained-volume disposition.
"""

from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

from control_plane_kit_core.secrets import SecretReference, SecretValue
from control_plane_kit_interpreters.cloudflare import CloudflareApiClient, CloudflareApiNotFound, CloudflareZoneAuthority
from products.cpk_server.tests.live_child_api import installation_from_input, save
from control_plane_kit_servers_cpk_server.client.installation import child_installation_document


ROOT = Path('/witness')
PREFIX = 'org.openj92.cpk.'


def provider(release):
    with (ROOT / 'inputs' / 'cloudflare-token').open('rb') as stream:
        token = stream.read(65_537)
    assert 0 < len(token) <= 65_536
    authority = CloudflareZoneAuthority(release['account_id'], release['zone_id'], release['zone_name'],
        SecretReference(f'secret://control-plane-kit/{release["parent_workspace_id"]}/cloudflare-api'), release['hostname'])
    text = token.decode('ascii')
    assert not any(character.isspace() for character in text)
    return CloudflareApiClient(authority, SecretValue(text))


def _context(release):
    import docker
    engine = docker.from_env()
    try:
        receipt = json.loads((ROOT / 'state' / 'receipt.json').read_bytes())
        assert receipt['phase'] == 'complete' and receipt['pending'] is None
        assert receipt['labels'][PREFIX + 'installation'] == release['parent_installation_id']
        assert engine.info()['ID'] == receipt['engine_id']
        return engine
    except BaseException:
        engine.close()
        raise


def _labels(resource, *, container=False):
    return resource.attrs['Config']['Labels'] if container else resource.attrs['Labels']


def _owner(labels, workspace, plan, *, node=None):
    assert labels.get(PREFIX + 'workspace') == workspace and labels.get(PREFIX + 'plan') == plan
    assert labels.get(PREFIX + 'fingerprint') and labels.get(PREFIX + 'desired-graph')
    if node is not None:
        assert labels.get(PREFIX + 'node') == node


def observe(release):
    """After API success, record exact resources for later absence/retention proof."""
    record = json.loads((ROOT / 'child-api' / 'record.json').read_bytes())
    assert record['phase'] == 'deployed'
    state = ROOT / 'child-resources'
    state.mkdir(mode=0o700, exist_ok=False)
    evidence = {'phase': 'observing', 'pending': None, 'containers': [], 'networks': [], 'volumes': []}
    save(state, evidence)
    value = json.loads((ROOT / 'child-input.json').read_bytes())
    document = child_installation_document(installation_from_input(value['installation']),
                                            child_workspace_id=release['child_workspace_id'])
    engine = _context(release)
    try:
        evidence['engine_id'] = engine.info()['ID']
        workspace, plan = release['parent_workspace_id'], record['parent_deployed']['plan_id']
        containers = engine.containers.list(all=True, filters={'label': [PREFIX + 'workspace=' + workspace,
                                                                       PREFIX + 'plan=' + plan]})
        assert len(containers) == 4
        expected_nodes = set(document['graph']['nodes'])
        assert {container.labels.get(PREFIX + 'node') for container in containers} == expected_nodes
        for container in containers:
            node = container.labels[PREFIX + 'node']
            _owner(container.labels, workspace, plan, node=node)
            assert container.attrs['State']['Running']
            logs = container.logs(tail=1000)
            assert len(logs) <= 1_048_576, 'child log evidence exceeds fixture bound'
            for path in (ROOT / 'child-material').iterdir():
                assert path.read_bytes() not in logs, 'child material found in product logs'
            evidence['containers'].append({'id': container.id, 'node_id': node, 'workspace_id': workspace, 'plan_id': plan})
            for mount in container.attrs['Mounts']:
                if mount['Type'] != 'volume':
                    continue
                volume = engine.volumes.get(mount['Name'])
                labels = _labels(volume)
                _owner(labels, workspace, plan, node=node)
                kind = labels.get(PREFIX + 'volume.kind')
                assert kind in {'retained-data', 'secret-file', 'configuration'}
                evidence['volumes'].append({'id': volume.name, 'node_id': node, 'workspace_id': workspace,
                    'plan_id': plan, 'kind': kind, 'labels_sha256': sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()})
            save(state, evidence)
        assert len({item['id'] for item in evidence['volumes']}) == len(evidence['volumes']) <= 16
        assert {item['node_id'] for item in evidence['volumes'] if item['kind'] == 'retained-data'} == {
            release['child_installation_id'] + '-postgres', release['child_installation_id'] + '-secrets'}
        for workspace, plan in ((workspace, plan),
                                (release['child_workspace_id'], record['child_runtime_deployed']['plan_id'])):
            networks = engine.networks.list(filters={'label': [PREFIX + 'workspace=' + workspace, PREFIX + 'plan=' + plan]})
            assert len(networks) == 1
            network = networks[0]
            _owner(_labels(network), workspace, plan)
            evidence['networks'].append({'id': network.id, 'workspace_id': workspace, 'plan_id': plan})
        client = provider(release)
        dns = client.list_dns_records_for_hostname(release['hostname'])
        assert len(dns) == 1 and dns[0]['name'] == release['hostname'] and dns[0]['type'] == 'CNAME'
        assert dns[0]['proxied'] is True
        content = dns[0]['content']
        suffix = '.cfargotunnel.com'
        assert content.endswith(suffix)
        tunnel_id = content[:-len(suffix)]
        assert str(UUID(tunnel_id)) == tunnel_id
        tunnel = client.get_tunnel(tunnel_id)
        assert tunnel['id'] == tunnel_id and tunnel.get('deleted_at') is None
        evidence['ingress'] = {'hostname': release['hostname'], 'dns_record_id': dns[0]['id'], 'tunnel_id': tunnel_id}
        evidence['phase'] = 'observed'
        save(state, evidence)
        print('child fixture: exact compute/volume identities and named ingress observed')
    finally:
        engine.close()


def preflight(release):
    """Exact cached products and unused named ingress; no acquisition or pull."""
    from control_plane_kit_servers_cpk_server.bootstrap import matches_image_reference
    state = ROOT / 'child-preflight'
    state.mkdir(mode=0o700, exist_ok=False)
    child = installation_from_input(json.loads((ROOT / 'child-input.json').read_bytes())['installation'])
    engine = _context(release)
    try:
        images = {}
        for name in ('cpk_product', 'postgres_product', 'secrets_product', 'connector_product'):
            reference = getattr(child, name).product.image.execution_reference
            image = engine.images.get(reference)
            assert matches_image_reference(reference, tuple(image.attrs['RepoDigests']))
            images[reference] = image.id
        assert provider(release).list_dns_records_for_hostname(release['hostname']) == []
        save(state, {'phase': 'complete', 'engine_id': engine.info()['ID'], 'cached_images': images,
                     'hostname': release['hostname'], 'hostname_absent': True, 'fresh_pull_proof': False})
    finally:
        engine.close()


def finish(release):
    """No compute deletion; verify API teardown, then chosen exact-volume cleanup."""
    import docker
    record = json.loads((ROOT / 'child-api' / 'record.json').read_bytes())
    assert record['phase'] == 'complete'
    state = ROOT / 'child-resources'
    evidence = json.loads((state / 'record.json').read_bytes())
    assert evidence['phase'] == 'observed' and evidence['pending'] is None
    assert release['retained_disposition'] in {'retain', 'delete-owned-fixture-volumes'}
    engine = _context(release)
    try:
        assert engine.info()['ID'] == evidence['engine_id']
        evidence['phase'] = 'checking-removal'
        save(state, evidence)
        for kind in ('containers', 'networks'):
            for item in evidence[kind]:
                try:
                    getattr(engine, kind).get(item['id'])
                except docker.errors.NotFound:
                    continue
                raise AssertionError('API teardown left a recorded compute resource')
        client = provider(release)
        ingress = evidence['ingress']
        dns_absent = False
        try:
            client.get_dns_record(ingress['dns_record_id'])
        except CloudflareApiNotFound:
            dns_absent = True
        assert dns_absent, 'owned DNS record remains after API teardown'
        assert client.list_dns_records_for_hostname(ingress['hostname']) == []
        tunnel_absent = False
        try:
            tunnel = client.get_tunnel(ingress['tunnel_id'])
        except CloudflareApiNotFound:
            tunnel_absent = True
        else:
            tunnel_absent = tunnel['id'] == ingress['tunnel_id'] and bool(tunnel.get('deleted_at'))
        assert tunnel_absent, 'owned tunnel remains active'
        for item in evidence['volumes']:
            volume = engine.volumes.get(item['id'])
            labels = _labels(volume)
            _owner(labels, item['workspace_id'], item['plan_id'], node=item['node_id'])
            assert sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest() == item['labels_sha256']
            if release['retained_disposition'] == 'delete-owned-fixture-volumes':
                evidence['pending'] = {'remove_volume': item['id']}
                save(state, evidence)
                volume.remove()  # No force: a still-used volume must stop cleanup.
                volume_absent = False
                try:
                    engine.volumes.get(item['id'])
                except docker.errors.NotFound:
                    volume_absent = True
                assert volume_absent, 'owned fixture volume remains'
                item['disposition'] = 'deleted'
                evidence['pending'] = None
            else:
                item['disposition'] = 'retained'
            save(state, evidence)
        evidence['phase'] = 'complete'
        save(state, evidence)
        print('child fixture: API compute/ingress removal verified; exact retained-resource disposition recorded')
    finally:
        engine.close()
