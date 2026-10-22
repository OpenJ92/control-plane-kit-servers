"""Product-owned release evidence policy; no credentials or runtime semantics."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

REPOSITORY = 'ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector'


def require(condition):
    if not condition:
        raise ValueError('Managed release evidence is invalid')


def hexadecimal(value, length):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def identity(value):
    return type(value) is str and value.startswith('sha256:') and hexadecimal(value[7:], 64)


def destination(source, tag):
    require(hexadecimal(source, 40) and tag == 'managed-' + source)
    return REPOSITORY + ':' + tag


def read_json(path, limit=65536):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit)
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        require(len(raw) <= limit)
        def unique(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result)
                result[key] = value
            return result
        return json.loads(raw, object_pairs_hook=unique)
    finally:
        os.close(descriptor)


def controller_receipt(value, image_id):
    require(type(value) is dict and set(value) == {
        'schema', 'source_commit', 'source_tree', 'dockerfile_sha256',
        'image_id', 'build_exit', 'build_log_sha256'})
    require(value['schema'] == 'cpk.cloudflared-controller-acquisition.v1')
    require(identity(image_id) and value['image_id'] == image_id)
    require(type(value['build_exit']) is int and value['build_exit'] == 0)
    for key in ('source_commit', 'source_tree'):
        require(hexadecimal(value[key], 40))
    for key in ('dockerfile_sha256', 'build_log_sha256'):
        require(hexadecimal(value[key], 64))
    return value


def package_evidence(package, pages, source, digest=None):
    tag = 'managed-' + source
    destination(source, tag)
    require(type(package) is dict and package.get('name') == 'control-plane-kit-servers/cloudflared-connector'
            and package.get('package_type') == 'container' and package.get('visibility') == 'private'
            and type(package.get('id')) is int and package['id'] > 0)
    require(type(pages) is list and bool(pages))
    found, ids = [], set()
    for page in pages:
        require(type(page) is list)
        for version in page:
            require(type(version) is dict and type(version.get('id')) is int and version['id'] > 0)
            require(version['id'] not in ids)
            ids.add(version['id'])
            require(identity(version.get('name')))
            metadata = version.get('metadata')
            require(type(metadata) is dict and type(metadata.get('container')) is dict)
            tags = metadata['container'].get('tags')
            require(type(tags) is list and all(type(t) is str for t in tags) and len(set(tags)) == len(tags))
            if tag in tags:
                found.append(version)
    if digest is None:
        require(not found)
    else:
        require(identity(digest) and len(found) == 1 and found[0]['name'] == digest)
    return {'package_id': package['id'], 'visibility': 'private', 'tag': tag,
            'digest': digest, 'version_id': found[0]['id'] if found else None}


def qualified_candidate(receipt, candidate_id, source):
    require(type(receipt) is dict and receipt.get('schema') == 'cpk.cloudflared-managed-qualification.v1')
    require(identity(candidate_id) and hexadecimal(source, 40))
    require(receipt.get('candidate_id') == candidate_id and receipt.get('source_commit') == source
            and receipt.get('status') == 'pass' and receipt.get('cleanup') == 'verified'
            and receipt.get('candidate_retained') is True)


def digest_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_receipt(path, value):
    raw = json.dumps(value, sort_keys=True).encode()
    require(len(raw) <= 65536)
    temporary = path.with_suffix('.tmp')
    with temporary.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def cleanup_owned(client, run, owned):
    """Never adopt an unrecorded object merely because its label matches."""
    import docker
    require(type(owned) is list and all(hexadecimal(item, 64) for item in owned))
    require(len(set(owned)) == len(owned))
    matching = client.containers.list(all=True, filters={'label': 'org.openj92.cpk.test-run=' + run})
    require(all(container.id in owned for container in matching))
    for identity_value in owned:
        try:
            container = client.containers.get(identity_value)
        except docker.errors.NotFound:
            continue
        container.reload()
        require(container.id == identity_value and
                container.attrs['Config'].get('Labels', {}).get('org.openj92.cpk.test-run') == run)
        container.remove(force=True)
        require(not client.containers.list(all=True, filters={'id': identity_value}))
    require(not client.containers.list(all=True, filters={'label': 'org.openj92.cpk.test-run=' + run}))


def qualify(root=Path('/source'), evidence=Path('/evidence')):
    """Run the unchanged packaged controller against one borrowed candidate."""
    import contextlib
    import docker
    sys.path.insert(0, str(root / 'products/cloudflared_connector/tests'))
    import packaged_managed_witness as witness
    candidate = os.environ['CPK_MANAGED_IMAGE']
    source = os.environ['CPK_MANAGED_SOURCE']
    run = os.environ['CPK_MANAGED_TEST_RUN']
    receipt = {'schema': 'cpk.cloudflared-managed-qualification.v1',
               'candidate_id': candidate, 'source_commit': source,
               'status': 'running', 'cleanup': 'unverified', 'candidate_retained': False,
               'run': run, 'controller_id': os.environ['CPK_RELEASE_CONTROLLER'],
               'source_tree': os.environ['CPK_RELEASE_TREE'],
               'recipe_sha256': digest_file(root / 'products/cloudflared_connector/Dockerfile.managed'),
               'witness_sha256': digest_file(root / 'products/cloudflared_connector/tests/packaged_managed_witness.py'),
               'controller_receipt_sha256': digest_file(evidence / 'controller.json')}
    path = evidence / 'qualification.json'
    write_receipt(path, receipt)
    client = None
    try:
        controller = controller_receipt(read_json(evidence / 'controller.json'), receipt['controller_id'])
        require(controller['source_commit'] == source and controller['source_tree'] == receipt['source_tree'])
        require(controller['dockerfile_sha256'] == digest_file(root / 'Dockerfile.test'))
        client = docker.from_env(timeout=5)
        image = client.images.get(candidate)
        require(image.id == candidate and image.attrs['Os'] == 'linux' and image.attrs['Architecture'] == 'amd64')
        require(image.attrs['Config'].get('Labels', {}).get('org.opencontainers.image.revision') == source)
        witness.verify_image(image)
        receipt['platform'] = 'linux/amd64'
        write_receipt(path, receipt)
        # The existing witness emits closed bounded diagnostics and never raw Docker exceptions.
        with (evidence / 'witness.log').open('x') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            witness.controller()
        receipt['status'] = 'pass'
    except Exception:
        receipt['status'] = 'fail'
    finally:
        if client is not None:
            try:
                records = evidence / 'fixtures/containers.json'
                owned = read_json(records) if records.exists() else []
                cleanup_owned(client, run, owned)
                receipt['cleanup'] = 'verified'
                receipt['candidate_retained'] = client.images.get(candidate).id == candidate
            except Exception:
                receipt['status'] = 'fail'
            finally:
                try:
                    client.close()
                except Exception:
                    receipt['status'] = 'fail'
                    receipt['cleanup'] = 'unverified'
        records = evidence / 'fixtures/containers.json'
        if records.is_file():
            try:
                receipt['created_containers'] = read_json(records)
            except Exception:
                receipt['status'] = 'fail'
        if (evidence / 'witness.log').is_file():
            receipt['witness_log_sha256'] = digest_file(evidence / 'witness.log')
        try:
            require(receipt['cleanup'] == 'verified')
            fixtures = evidence / 'fixtures'
            results = fixtures / 'results'
            if results.exists():
                preserved = evidence / 'witness-results'
                preserved.mkdir()
                for item in results.iterdir():
                    require(re.fullmatch(r'cpk-witness-[0-9a-f]+\.json', item.name) is not None)
                    value = read_json(item, 4096)
                    write_receipt(preserved / item.name, value)
                    item.unlink()
                results.rmdir()
            if records.exists():
                records.unlink()
            fixtures.rmdir()  # Unknown files fail closed; no recursive removal.
        except Exception:
            receipt['status'] = 'fail'
            receipt['cleanup'] = 'unverified'
        write_receipt(path, receipt)
    qualified_candidate(receipt, candidate, source)


def main():
    mode, *args = sys.argv[1:]
    if mode == 'package':
        root, source, *digest = args
        result = package_evidence(read_json(Path(root) / 'package.json'),
                                  read_json(Path(root) / 'versions.json', 4 * 1024 * 1024), source,
                                  digest[0] if digest else None)
        print(json.dumps(result))
    elif mode == 'qualified':
        path, candidate, source = args
        qualified_candidate(read_json(path), candidate, source)
    elif mode == 'qualify':
        require(not args)
        qualify()
    else:
        raise ValueError('Unknown managed release mode')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Managed release evidence did not pass', file=sys.stderr)
        raise SystemExit(1)
