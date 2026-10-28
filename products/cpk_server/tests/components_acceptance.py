"""Registered components through the real authenticated factory and owner stores."""
import json
from urllib.parse import quote, urlencode

from control_plane_kit_core.configuration import ConfigurationArtifact, ConfigurationArtifactRequirement, ConfigurationMediaType
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.products import ContainerServerProduct, OciImageReference, ProductDescriptorCodec, ProductIdentity, ProductRuntimeContract
from control_plane_kit_core.secrets import SecretReference, SecretReferenceEnvironmentDelivery

from receiver_acceptance_operations import utc_now


def components_acceptance(client, app, administrator_credential, operator_credential, operator):
    """Extend the existing isolated dynamic-authority witness, without provider IO."""
    workspace = 'workspace-components'

    def call(surface, route_id, payload=None, *, digest=None, target=workspace, credential=None, status=200):
        route = app.state.http_boundary.composition.http_api.route(route_id)
        payload = dict(payload or {})
        headers = {'Authorization': 'Bearer ' + (credential or operator_credential)}
        if surface == 'http':
            path = route.path_template.replace('{workspace_id}', quote(target, safe=''))
            if digest is not None:
                path = path.replace('{descriptor_sha256}', quote(digest, safe=''))
            if route.method.value == 'GET':
                query = {key: json.dumps(value) if isinstance(value, dict) else value for key, value in payload.items()}
                response = client.get(path + ('?' + urlencode(query, quote_via=quote) if query else ''), headers=headers)
            else:
                response = client.post(path, json=payload, headers=headers)
        else:
            read = route.method.value == 'GET'
            parity = app.state.http_boundary.composition.handoff
            bindings = parity.projection_parity.projections if read else parity.command_parity.commands
            name = next(binding.mcp_tool_name for binding in bindings if binding.http_route_id == route_id)
            if '{workspace_id}' in route.path_template:
                payload['workspace_id'] = target
            if digest is not None:
                payload['descriptor_sha256'] = digest
            method = 'resources/read' if read else 'tools/call'
            response = client.post('/mcp', headers={**headers, 'Accept': 'application/json',
                'MCP-Protocol-Version': '2025-06-18', 'Mcp-Method': method}, json={
                    'jsonrpc': '2.0', 'id': 'components', 'method': method,
                    'params': {'name': name, 'arguments': payload}})
        assert response.status_code == status, (surface, route_id, response.status_code, status)
        assert len(response.content) <= 1048576
        for private in (administrator_credential, operator_credential,
                        'COMPONENT_PRIVATE_FILE', 'COMPONENT_PRIVATE_ENV', 'COMPONENT_PRIVATE_HANDLE'):
            assert private not in response.text
        result = response.json()
        return result['result'] if surface == 'mcp' and status == 200 else result

    call('http', 'command.workspace-administration.create', {'workspace_id': workspace,
        'name': 'Components', 'idempotency_key': 'components-create'}, credential=administrator_credential)
    for surface in ('http', 'mcp'):
        call(surface, 'read.products', status=403)
    grant = call('http', 'command.workspace-permission.grant', {'target': operator.descriptor(),
        'scopes': [PolicyScope.INSTANCE_WORKSPACE_READ.value, PolicyScope.INSTANCE_WORKSPACE_EDIT.value],
        'expected_revision': 0, 'idempotency_key': 'components-permission'}, credential=administrator_credential)
    assert grant
    assert call('http', 'read.products')['items'] == []

    references = {}
    for mixed in (False, True):
        name = 'mixed' if mixed else 'required-only'
        document = ProductDescriptorCodec().encode_document(ContainerServerProduct(
            ProductIdentity('components-test', name, 1),
            OciImageReference('example.invalid', name, 'sha256:' + 'a' * 64),
            ProductRuntimeContract(
                public_environment=(PublicStaticEnvironmentBinding('LABEL', 'COMPONENT_PRIVATE_ENV'),),
                configuration_requirements=(ConfigurationArtifactRequirement('required', '/etc/required.json', ConfigurationMediaType.JSON),),
                configuration_artifacts=(ConfigurationArtifact('defaults', '/etc/defaults.txt',
                    ConfigurationMediaType.TEXT, 'COMPONENT_PRIVATE_FILE'),) if mixed else (),
                secret_deliveries=(SecretReferenceEnvironmentDelivery('HANDLE',
                    SecretReference('secret://local/COMPONENT_PRIVATE_HANDLE')),)),
            display_name=name, description='Untrusted component description.'))
        imported = call('http', 'command.product.import', {'descriptor_document': json.loads(document.content),
            'imported_at': utc_now(), 'idempotency_key': 'components-import-' + name})
        references[imported['reference']['descriptor_sha256']] = (imported['reference'], mixed)

    first = call('http', 'read.products', {'limit': 1})
    assert first == call('mcp', 'read.products', {'limit': 1})
    assert first['next_cursor'] is not None
    second = call('http', 'read.products', {'limit': 1, 'after': first['next_cursor']})
    assert second == call('mcp', 'read.products', {'limit': 1, 'after': first['next_cursor']})
    assert second['next_cursor'] is None
    items = first['items'] + second['items']
    assert [item['reference']['descriptor_sha256'] for item in items] == sorted(references)
    for digest, (reference, mixed) in references.items():
        detail = call('http', 'read.product-detail', digest=digest)
        assert detail == call('mcp', 'read.product-detail', digest=digest)
        assert detail['product']['reference'] == reference
        assert detail['product']['projection_kind'] == 'noncanonical-product-display'
        assert detail['product']['status'] == 'active'
        slots = detail['product']['contract']['configuration']
        assert [slot['artifact_id'] for slot in slots] == (['defaults', 'required'] if mixed else ['required'])
        assert all(set(slot) == {'artifact_id', 'target_path', 'media_type', 'file_mode'} for slot in slots)
    for surface in ('http', 'mcp'):
        call(surface, 'read.products', {'limit': 101}, status=400)
        foreign_cursor = {**first['next_cursor'], 'scope': {'workspace_id': 'workspace-b'}}
        call(surface, 'read.products', {'after': foreign_cursor}, status=400)
        call(surface, 'read.products', target='workspace-b', status=403)
        call(surface, 'read.product-detail', digest=next(iter(references)), target='workspace-b', status=403)
        call(surface, 'read.product-detail', digest='A' * 64, status=400)
        call(surface, 'read.product-detail', digest='0' * 64, status=404)
        call(surface, 'read.products', credential='synthetic-components-invalid', status=401)
    print('components: actual authenticated HTTP/MCP, dynamic workspace authority, owner-store paging and safe v2 detail passed', flush=True)
