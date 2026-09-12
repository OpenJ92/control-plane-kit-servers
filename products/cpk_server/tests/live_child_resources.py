"""Exact-resource reads and separately released retained-volume disposition.

Never deploys, repairs or removes child compute. Public API convergence precedes
absence checks. Every read and retained deletion is bound to the one-run release.
"""

from hashlib import sha256
import json
from pathlib import Path
from uuid import UUID

from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.secrets import SecretReference, SecretValue
from control_plane_kit_interpreters.cloudflare import CloudflareApiClient, CloudflareApiNotFound, CloudflareZoneAuthority
from products.cpk_server.tests.live_child_api import application_graph, installation_from_input, save
from control_plane_kit_servers_cpk_server.client.installation import child_installation_document


ROOT = Path('/witness')
PREFIX = 'org.openj92.cpk.'


def provider(release, hostname):
    assert hostname in {release['hostname'], release['gateway_hostname']}
    with (ROOT / 'inputs' / 'cloudflare-token').open('rb') as stream:
        token = stream.read(65_537)
    assert 0 < len(token) <= 65_536
    authority = CloudflareZoneAuthority(release['account_id'], release['zone_id'], release['zone_name'],
        SecretReference(f'secret://control-plane-kit/{release["parent_workspace_id"]}/cloudflare-api'), hostname)
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


def _observe_compute(engine, state, evidence, *, workspace, plan, nodes, group):
    from control_plane_kit_interpreters.docker.sdk import matches_image_reference
    containers = engine.containers.list(all=True, filters={'label': [PREFIX + 'workspace=' + workspace,
                                                                   PREFIX + 'plan=' + plan]})
    assert len(containers) == len(nodes) == 4
    assert {container.labels.get(PREFIX + 'node') for container in containers} == set(nodes)
    for container in containers:
        node = container.labels[PREFIX + 'node']
        _owner(container.labels, workspace, plan, node=node)
        assert container.attrs['State']['Running']
        reference = nodes[node].metadata['oci_image']
        assert matches_image_reference(reference, tuple(container.image.attrs['RepoDigests']))
        logs = container.logs(tail=1000)
        assert len(logs) <= 1_048_576, 'child log evidence exceeds fixture bound'
        for path in (ROOT / 'child-material').iterdir():
            assert path.read_bytes() not in logs, 'child material found in product logs'
        evidence['containers'].append({'id': container.id, 'node_id': node, 'workspace_id': workspace,
                                      'plan_id': plan, 'group': group, 'image_id': container.image.id})
        for mount in container.attrs['Mounts']:
            if mount['Type'] != 'volume':
                continue
            volume = engine.volumes.get(mount['Name'])
            labels = _labels(volume)
            _owner(labels, workspace, plan, node=node)
            kind = labels.get(PREFIX + 'volume.kind')
            assert kind in {'retained-data', 'secret-file', 'configuration'}
            assert group == 'installation' or kind != 'retained-data'
            evidence['volumes'].append({'id': volume.name, 'node_id': node, 'workspace_id': workspace,
                'plan_id': plan, 'group': group, 'kind': kind,
                'labels_sha256': sha256(json.dumps(labels, sort_keys=True).encode()).hexdigest()})
        save(state, evidence)
    assert len({item['id'] for item in evidence['volumes']}) == len(evidence['volumes']) <= 24
    networks = engine.networks.list(filters={'label': [PREFIX + 'workspace=' + workspace, PREFIX + 'plan=' + plan]})
    assert len(networks) == 1
    network = networks[0]
    _owner(_labels(network), workspace, plan)
    evidence['networks'].append({'id': network.id, 'workspace_id': workspace, 'plan_id': plan, 'group': group})
    save(state, evidence)


def _observe_ingress(release, hostname):
    client = provider(release, hostname)
    dns = client.list_dns_records_for_hostname(hostname)
    assert len(dns) == 1 and dns[0]['name'] == hostname and dns[0]['type'] == 'CNAME'
    assert dns[0]['proxied'] is True
    content = dns[0]['content']
    suffix = '.cfargotunnel.com'
    assert content.endswith(suffix)
    tunnel_id = content[:-len(suffix)]
    assert str(UUID(tunnel_id)) == tunnel_id
    tunnel = client.get_tunnel(tunnel_id)
    assert tunnel['id'] == tunnel_id and tunnel.get('deleted_at') is None
    return {'hostname': hostname, 'dns_record_id': dns[0]['id'], 'tunnel_id': tunnel_id}


def observe_installation(release):
    """Bind the deployed parent's exact namespace before initial local custody."""
    from control_plane_kit_core.topology import GraphDescriptorCodec
    record = json.loads((ROOT / 'child-api' / 'record.json').read_bytes())
    assert record['phase'] == 'parent-initialized' and record['pending'] is None
    state = ROOT / 'child-resources'
    state.mkdir(mode=0o700, exist_ok=False)
    evidence = {'phase': 'observing-installation', 'pending': None, 'containers': [], 'networks': [],
                'volumes': [], 'ingresses': {}, 'installation_plan_id': record['parent_deployed']['plan_id'],
                'child_workspace_id': release['child_workspace_id']}
    save(state, evidence)
    value = json.loads((ROOT / 'child-input.json').read_bytes())
    installation = installation_from_input(value['installation'])
    graph = GraphDescriptorCodec().decode(child_installation_document(installation,
        child_workspace_id=release['child_workspace_id'])['graph'])
    engine = _context(release)
    try:
        evidence['engine_id'] = engine.info()['ID']
        _observe_compute(engine, state, evidence, workspace=release['parent_workspace_id'],
            plan=evidence['installation_plan_id'], nodes=graph.nodes,
            group='installation')
        assert {item['node_id'] for item in evidence['volumes'] if item['kind'] == 'retained-data'} == {
            release['child_installation_id'] + '-postgres', release['child_installation_id'] + '-secrets'}
        evidence['child_cpk_container_id'] = next(item['id'] for item in evidence['containers']
                                               if item['node_id'] == installation.cpk_node_id)
        evidence['ingresses']['installation'] = _observe_ingress(release, release['hostname'])
        evidence['phase'] = 'installation-observed'
        save(state, evidence)
        print('child fixture: exact parent installation and custody namespace observed')
    finally:
        engine.close()


def observe(release):
    """Record application ownership separately from the parent installation."""
    record = json.loads((ROOT / 'child-api' / 'record.json').read_bytes())
    assert record['phase'] == 'deployed' and record['pending'] is None
    state = ROOT / 'child-resources'
    evidence = json.loads((state / 'record.json').read_bytes())
    assert evidence['phase'] == 'installation-observed' and evidence['pending'] is None
    assert evidence['installation_plan_id'] == record['parent_deployed']['plan_id']
    value = json.loads((ROOT / 'child-input.json').read_bytes())
    graph = application_graph(installation_from_input(value['installation']), release['child_workspace_id'])
    engine = _context(release)
    try:
        assert engine.info()['ID'] == evidence['engine_id']
        evidence['phase'] = 'observing-application'
        save(state, evidence)
        _observe_compute(engine, state, evidence, workspace=release['child_workspace_id'],
            plan=record['child_runtime_deployed']['plan_id'],
            nodes=graph.nodes, group='application')
        evidence['ingresses']['application'] = _observe_ingress(release, release['gateway_hostname'])
        evidence['phase'] = 'observed'
        save(state, evidence)
        print('child fixture: exact four-product application and its named gateway ingress observed')
    finally:
        engine.close()


def preflight(release):
    """Exact cached products and two unused named ingresses; no acquisition."""
    from control_plane_kit_interpreters.docker.sdk import matches_image_reference
    state = ROOT / 'child-preflight'
    state.mkdir(mode=0o700, exist_ok=False)
    value = json.loads((ROOT / 'child-input.json').read_bytes())
    child = installation_from_input(value['installation'])
    products = [getattr(child, name).product for name in
                ('cpk_product', 'postgres_product', 'secrets_product', 'connector_product')]
    products.extend(ProductDescriptorCodec().decode_document(document).product
                    for document in value['application']['products'].values())
    engine = _context(release)
    try:
        images = {}
        for product in products:
            reference = product.image.execution_reference
            image = engine.images.get(reference)
            assert matches_image_reference(reference, tuple(image.attrs['RepoDigests']))
            images[reference] = image.id
        hostnames = (release['hostname'], release['gateway_hostname'])
        assert len(set(hostnames)) == 2
        for hostname in hostnames:
            assert provider(release, hostname).list_dns_records_for_hostname(hostname) == []
        save(state, {'phase': 'complete', 'engine_id': engine.info()['ID'], 'cached_images': images,
                     'absent_hostnames': list(hostnames), 'fresh_pull_proof': False})
    finally:
        engine.close()


def _verify_compute_absent(engine, evidence, *, group=None):
    import docker
    for kind in ('containers', 'networks'):
        for item in evidence[kind]:
            if group is not None and item['group'] != group:
                continue
            try:
                getattr(engine, kind).get(item['id'])
            except docker.errors.NotFound:
                continue
            raise AssertionError('API teardown left a recorded compute resource')


def _verify_ingress_absent(release, ingress):
    client = provider(release, ingress['hostname'])
    dns_absent = False
    try:
        client.get_dns_record(ingress['dns_record_id'])
    except CloudflareApiNotFound:
        dns_absent = True
    assert dns_absent, 'owned DNS record remains after API teardown'
    assert client.list_dns_records_for_hostname(ingress['hostname']) == []
    try:
        tunnel = client.get_tunnel(ingress['tunnel_id'])
    except CloudflareApiNotFound:
        return
    assert tunnel['id'] == ingress['tunnel_id'] and bool(tunnel.get('deleted_at')), 'owned tunnel remains active'


def verify_application_empty(release):
    """Read-only removal proof required before the parent can be torn down."""
    record = json.loads((ROOT / 'child-api' / 'record.json').read_bytes())
    assert record['phase'] == 'application-empty' and record['pending'] is None
    assert record['child_empty']['compute_graph'] == 'empty'
    state = ROOT / 'child-resources'
    evidence = json.loads((state / 'record.json').read_bytes())
    assert evidence['phase'] == 'observed' and evidence['pending'] is None
    engine = _context(release)
    try:
        assert engine.info()['ID'] == evidence['engine_id']
        evidence['phase'] = 'checking-application-removal'
        save(state, evidence)
        _verify_compute_absent(engine, evidence, group='application')
        _verify_ingress_absent(release, evidence['ingresses']['application'])
        evidence['application_empty_plan_id'] = record['child_empty']['tracking']['plan_id']
        evidence['phase'] = 'application-removed'
        save(state, evidence)
        print('child fixture: exact application compute and gateway ingress absent before parent teardown')
    finally:
        engine.close()


def finish(release):
    """No compute deletion; verify API teardown, then chosen exact-volume cleanup."""
    import docker
    record = json.loads((ROOT / 'child-api' / 'record.json').read_bytes())
    assert record['phase'] == 'complete' and record['pending'] is None
    state = ROOT / 'child-resources'
    evidence = json.loads((state / 'record.json').read_bytes())
    assert evidence['phase'] == 'application-removed' and evidence['pending'] is None
    assert release['retained_disposition'] in {'retain', 'delete-owned-fixture-volumes'}
    engine = _context(release)
    try:
        assert engine.info()['ID'] == evidence['engine_id']
        evidence['phase'] = 'checking-removal'
        save(state, evidence)
        _verify_compute_absent(engine, evidence)
        for ingress in evidence['ingresses'].values():
            _verify_ingress_absent(release, ingress)
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
