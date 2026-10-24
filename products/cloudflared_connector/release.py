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
PUSH_LIMIT = 1048576


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


def read_push_bytes(path, limit=PUSH_LIMIT):
    """Bounded stable regular bytes; never follow a file or ancestor symlink."""
    path = Path(path)
    require(path.is_absolute() and path.anchor == '/' and '..' not in path.parts)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        file_fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            before = os.fstat(file_fd)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= limit)
            with os.fdopen(file_fd, 'rb', closefd=False) as stream:
                raw = stream.read(limit + 1)
            after = os.fstat(file_fd)
            require(len(raw) == before.st_size and len(raw) <= limit and
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns))
            return raw
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


def producer_profile(version, info):
    """Only the reviewed Moby classic layer-store push path is supported."""
    require(type(version) is dict and version == dict(
        Version='28.0.4', GitCommit='6430e49', Os='linux', Arch='amd64'))
    require(type(info) is dict and set(info) == {'ID','ServerVersion','OSType','Driver','DriverStatus'})
    require(info['ServerVersion'] == version['Version'] and info['OSType'] == 'linux'
            and info['Driver'] == 'overlay2')
    require(type(info['ID']) is str and re.fullmatch(r'[A-Za-z0-9:-]{1,128}', info['ID']))
    status = info['DriverStatus']
    require(type(status) is list and 0 < len(status) <= 32)
    for pair in status:
        require(type(pair) is list and len(pair) == 2 and all(type(v) is str and len(v) <= 256 for v in pair))
        require(pair[0] != 'driver-type')  # containerd snapshotter path is unreviewed.
    require(len({p[0] for p in status}) == len(status))
    return dict(version=version, info=info)


def push_receipt(raw, exit_code, source, tree, candidate, selected_destination):
    require(type(exit_code) is int and exit_code == 0)
    require(hexadecimal(tree, 40) and identity(candidate))
    require(selected_destination == destination(source, 'managed-' + source))
    require(type(raw) is bytes and 0 < len(raw) <= PUSH_LIMIT and raw.endswith(b'\n'))
    require(all(b == 10 or 32 <= b <= 126 for b in raw))
    lines = raw[:-1].split(b'\n')  # No trimming, newline normalization or loose digest search.
    terminal = re.fullmatch(rb'managed-([0-9a-f]{40}): digest: (sha256:[0-9a-f]{64}) size: ([1-9][0-9]{0,6})', lines[-1])
    require(terminal is not None and terminal[1].decode() == source)
    size = int(terminal[3]); require(size <= PUSH_LIMIT)
    header = ('The push refers to repository [' + REPOSITORY + ']').encode()
    for number, line in enumerate(lines[:-1]):
        require((number == 0 and line == header) or re.fullmatch(
            rb'[0-9a-f]{12}: (Preparing|Waiting|Pushed|Layer already exists|Mounted from [A-Za-z0-9._/-]+)', line))
    return dict(schema='cpk.cloudflared-managed-push.v1', source_commit=source,
                source_tree=tree, candidate_id=candidate, destination=selected_destination,
                manifest_digest=terminal[2].decode(), manifest_size=size,
                transcript_sha256=hashlib.sha256(raw).hexdigest())


def read_push_json(path):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value); value[key] = item
        return value
    return json.loads(read_push_bytes(path, 65536), object_pairs_hook=unique)


def push_anchor(root, source, tree, candidate, selected_destination):
    """Re-derive from original private evidence, not a trusted summary receipt."""
    root = Path(root)
    profiles = []
    for phase in ('before','after'):
        profiles.append(producer_profile(read_push_json(root/f'push-version-{phase}.json'),
                                         read_push_json(root/f'push-info-{phase}.json')))
        require(read_push_bytes(root/f'push-candidate-{phase}.id', 128) == (candidate+'\n').encode())
    require(profiles[0] == profiles[1])
    require(read_push_bytes(root/'push.exit', 8) == b'0\n')
    return push_receipt(read_push_bytes(root/'push.log'), 0, source, tree, candidate, selected_destination)


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
    elif mode == 'producer-profile':
        root, = args
        producer_profile(read_push_json(Path(root)/'push-version-before.json'),
                         read_push_json(Path(root)/'push-info-before.json'))
    elif mode == 'push-anchor':
        root, source, tree, candidate, selected_destination = args
        print(json.dumps(push_anchor(root, source, tree, candidate, selected_destination)))
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
