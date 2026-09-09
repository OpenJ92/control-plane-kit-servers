"""Root acquisition composition only; fake Docker is not public ingress proof."""

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

import docker

from control_plane_kit_servers_cpk_server import bootstrap, bootstrap_runtime
from test_root_bootstrap import installation_input, DRIVER, ROOT


class RootConnectionRuntimeTests(unittest.TestCase):
    def test_connector_follows_setup_and_preserves_identity_on_start_failure(self):
        document = installation_input()
        token = 'private-connection-test-token'
        configuration = {'config': {'ingress': [
            {'hostname': 'root.example.test', 'service': 'http://cpk-bootstrap-origin:8080', 'originRequest': {}},
            {'service': 'http_status:404'}]}}
        document['external_ingress_connection'] = {
            'tunnel_id': '11111111-1111-4111-8111-111111111111', 'dns_record_id': 'd' * 32,
            'token_reference': 'secret://bootstrap/retained-ingress/token',
            'token_sha256': sha256(token.encode()).hexdigest(),
            'configuration_sha256': sha256(bootstrap.canonical(configuration)).hexdigest(),
            'connector_product': json.loads((ROOT / 'products/cloudflared_connector/product.cpk.json').read_bytes())}
        plan = bootstrap.plan_root_bootstrap(document, driver_image_id=DRIVER)
        connection = plan['external_ingress_connection']
        material = {reference: 'private-fixture-value' for reference in plan['required_material']}
        material[connection['token_reference']] = token
        for fail_start in (False, True):
            with self.subTest(fail_start=fail_start), tempfile.TemporaryDirectory() as directory:
                state = Path(directory)
                events, containers, volumes, files = [], {}, {}, {}
                def image(reference):
                    return SimpleNamespace(image_id=reference if reference == DRIVER else reference.split('@')[1],
                        repo_digests=(reference,), secret_file_owner_uid=lambda: 0 if reference == DRIVER else 10001)
                def get_volume(identity):
                    if identity not in volumes:
                        raise docker.errors.NotFound('fixture volume absent')
                    return volumes[identity]
                def create_volume(*, name, labels):
                    volume = SimpleNamespace(id=name, attrs={'Labels': labels}, remove=lambda: volumes.pop(name))
                    volumes[name] = volume
                    return volume
                def create_container(image_id, **options):
                    name = options['name']
                    identity = 'returned-' + name
                    container = SimpleNamespace(id=identity, options=options,
                        attrs={'Image': image_id, 'State': {'Running': False}}, reload=lambda: None,
                        wait=lambda **kwargs: {'StatusCode': 0}, remove=lambda: containers.pop(identity))
                    def start():
                        events.append('start:' + name)
                        if name == connection['node_id']:
                            saved = json.loads((state / 'receipt.json').read_bytes())
                            self.assertEqual(saved['resources']['containers'][name]['id'], identity)
                            self.assertEqual(saved['pending'], 'start-external-ingress-connector')
                            if fail_start:
                                raise RuntimeError('connector start outcome uncertain')
                        container.attrs['State']['Running'] = True
                    container.start = start
                    containers[identity] = container
                    events.append('create:' + name)
                    if name == connection['node_id']:
                        saved = json.loads((state / 'receipt.json').read_bytes())
                        self.assertEqual(saved['observations']['public_setup']['status'], 'authenticated-local-setup')
                        self.assertIn('public-setup-observed', events)
                        self.assertEqual(options['environment'], {'TUNNEL_TOKEN_FILE': '/run/secrets/cpk-ingress/token'})
                        self.assertEqual(options['network'], 'returned-root-network')
                        self.assertNotIn('ports', options)
                        self.assertEqual(len(options['mounts']), 1)
                        mount = options['mounts'][0]
                        self.assertTrue(mount['ReadOnly'])
                        self.assertEqual(mount['Target'], '/run/secrets/cpk-ingress/token')
                        self.assertEqual(files[mount['Source']].mode, 0o400)
                        self.assertNotIn(token, json.dumps(options))
                    return container
                def inspect_container(identity):
                    container = containers[identity]
                    return SimpleNamespace(image_id=container.attrs['Image'], readonly_secret_mounts=tuple(
                        SimpleNamespace(target_path=mount['Target'], volume_name=mount['Source'])
                        for mount in container.options.get('mounts', []) if mount.get('ReadOnly')))
                def stage_file(name, value, mode, *, owner_uid):
                    files[name] = SimpleNamespace(regular_file=True, uid=owner_uid, mode=0o400,
                        content_digest=sha256(value.reveal().encode()).hexdigest())
                engine = SimpleNamespace(info=lambda: {'ID': 'test-engine'}, close=lambda: events.append('closed'),
                    api=SimpleNamespace(create_endpoint_config=lambda **kwargs: kwargs),
                    images=SimpleNamespace(get=lambda identity: SimpleNamespace(attrs={
                        'Config': {'Env': ['CPK_SECRETS_PROVIDER_ID=control-plane-kit']}})),
                    containers=SimpleNamespace(list=lambda **kwargs: [], create=create_container),
                    volumes=SimpleNamespace(create=create_volume, get=get_volume),
                    networks=SimpleNamespace(list=lambda **kwargs: [], create=lambda *args, **kwargs:
                        SimpleNamespace(id='returned-root-network')))
                sdk = SimpleNamespace(inspect_image=image, inspect_volume=lambda name: None,
                    materialize_secret_file=stage_file, inspect_secret_file=lambda name: files[name],
                    inspect_container=inspect_container,
                    run_http_probe=lambda **kwargs: SimpleNamespace(exit_code=0, classification='completed',
                        status_code=200, body_sha256_matches=True))
                def setup_progress(*args):
                    events.append('public-setup-observed')
                    return {'status': 'complete', 'pending': None, 'workspace_id': 'root-workspace',
                            'commands': [{'route': route} for route in plan['setup_routes']], 'reads': []}
                original_stat = bootstrap_runtime.os.stat
                def socket_stat(path, *args, **kwargs):
                    if str(path) == '/var/run/docker.sock':
                        return SimpleNamespace(st_gid=1234)
                    return original_stat(path, *args, **kwargs)
                with patch('docker.DockerClient', return_value=engine) as constructor, \
                        patch('control_plane_kit_interpreters.docker.DockerSdkClient', return_value=sdk), \
                        patch.object(bootstrap_runtime, '_postgres_ready', return_value=None), \
                        patch.object(bootstrap_runtime, '_setup_progress', side_effect=setup_progress), \
                        patch.object(bootstrap_runtime.os, 'stat', side_effect=socket_stat), \
                        patch.dict(bootstrap_runtime.os.environ, {'CPK_BOOTSTRAP_ENGINE_ID': 'test-engine'}):
                    if fail_start:
                        with self.assertRaisesRegex(RuntimeError, 'outcome uncertain'):
                            bootstrap_runtime._acquire(plan, material, state)
                    else:
                        result = bootstrap_runtime._acquire(plan, material, state)
                        self.assertEqual(result['status'], 'local-ready')
                    constructor.assert_called_once_with(base_url='unix:///var/run/docker.sock', timeout=30)
                receipt = json.loads((state / 'receipt.json').read_bytes())
                self.assertEqual(receipt['resources']['containers'][connection['node_id']]['id'],
                                 'returned-' + connection['node_id'])
                self.assertEqual(receipt['observations']['external_ingress_connection']['provider_disposition'],
                                 'operator-retained')
                self.assertEqual(receipt['phase'], 'acquiring' if fail_start else 'complete')
                self.assertEqual(receipt['pending'], 'start-external-ingress-connector' if fail_start else None)
                self.assertEqual(events.count('create:' + connection['node_id']), 1)
                self.assertEqual(events.count('start:' + connection['node_id']), 1)
                self.assertEqual(events[-1], 'closed')
