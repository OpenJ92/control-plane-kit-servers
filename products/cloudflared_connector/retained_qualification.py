"""One fixed retained-image qualification; existing release owners perform effects.

Run as a module from the orchestration checkout. Never import the historical
checkout as application code or modify its contents.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

from products.cloudflared_connector import release

SOURCE = 'cc1b8d87b7f895cb56153f3daf2e9683fb59bea2'
TREE = '1befc607151dc75d3156c359ec5454d426a472b9'
REFERENCE = ('ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector@'
             'sha256:812262a6cc6b2e6971492a37f9135655d4c7b82aedd5435a483476f77b642091')
INPUT_HASHES = {
    'Dockerfile.test': '6a49e7bc9ced4d5532cb474dcf847cef8853b717ed8f00d1d54c98676d1acf7c',
    'products/cloudflared_connector/Dockerfile.managed': 'bd6eabced841bc0defb20601f2d7c988c8fe8192e01009373a36e7a987ff5011',
    'products/cloudflared_connector/tests/packaged_managed_witness.py': '7707c0ac7b46169daafa1c392ae7ae651c7daf9f1151d7f17234d2d450bb006d',
}
ENGINE_COMMITS = {
    '28.0.4': '6430e49a55babd9b8f4d08e70ecb2b68900770fe',
    '28.5.1': 'f8215cc266744ef195a50a70d427c345da2acdbb',
}


def require(condition):
    if not condition:
        raise ValueError('Retained qualification admission failed')


def executor(info, version):
    require(info.get('OSType') == 'linux' and info.get('Architecture') in ('amd64', 'x86_64'))
    name, commit = version.get('Version'), version.get('GitCommit')
    require(type(name) is str and name in ENGINE_COMMITS and type(commit) is str)
    require(7 <= len(commit) <= 40 and ENGINE_COMMITS[name].startswith(commit))
    daemon = info.get('ID')
    require(type(daemon) is str and re.fullmatch(r'[a-zA-Z0-9:-]{1,128}', daemon))
    return {'daemon_id': daemon, 'version': name, 'commit': commit, 'platform': 'linux/amd64'}


def observed_executor(info, version):
    def bounded(value, pattern):
        return value if type(value) is str and re.fullmatch(pattern, value) else None
    return {'daemon_id': bounded(info.get('ID'), r'[a-zA-Z0-9:-]{1,128}'),
            'version': bounded(version.get('Version'), r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'),
            'commit': bounded(version.get('GitCommit'), r'[0-9a-f]{7,40}'),
            'platform': 'linux/amd64' if info.get('OSType') == 'linux'
                and info.get('Architecture') in ('amd64', 'x86_64') else None}


def association(image):
    require(release.identity(image.get('Id')) and REFERENCE in image.get('RepoDigests', []))
    require(image.get('Os') == 'linux' and image.get('Architecture') == 'amd64')
    require(image.get('Config', {}).get('Labels', {}).get('org.opencontainers.image.revision') == SOURCE)
    return image['Id']


def qualification_fields(value, candidate):
    require(value.get('schema') == 'cpk.cloudflared-managed-qualification.v1')
    require(value.get('candidate_id') == candidate and value.get('source_commit') == SOURCE)
    require(value.get('status') in ('running', 'pass', 'fail'))
    require(value.get('cleanup') in ('verified', 'unverified'))
    require(type(value.get('candidate_retained')) is bool)
    result = {key: value[key] for key in ('status', 'cleanup', 'candidate_retained')}
    for key in ('schema', 'candidate_id', 'source_commit'):
        result[key] = value[key]
    for key in ('controller_id',):
        require(release.identity(value.get(key)))
        result[key] = value[key]
    require(value.get('source_tree') == TREE)
    result['source_tree'] = TREE
    require(type(value.get('run')) is str and re.fullmatch(r'cpk-managed-release-run\.[a-zA-Z0-9]{1,64}', value['run']))
    result['run'] = value['run']
    require(value.get('platform') in (None, 'linux/amd64'))
    result['platform'] = value.get('platform')
    for key in ('recipe_sha256', 'witness_sha256', 'controller_receipt_sha256'):
        require(release.hexadecimal(value.get(key), 64))
        result[key] = value[key]
    witness_hash = value.get('witness_log_sha256')
    require(witness_hash is None or release.hexadecimal(witness_hash, 64))
    result['witness_log_sha256'] = witness_hash
    return result


def require_success(value):
    require(value.get('status') == 'pass' and value.get('cleanup') == 'verified'
            and value.get('candidate_retained') is True)


def save(root, report):
    release.write_receipt(root / 'result.json', report)


def finish(root, report, primary):
    report['primary_exit'] = primary
    report['status'] = 'pass' if primary == 0 else 'fail'
    try:
        save(root, report)
    except Exception:
        return primary or 1
    return primary


def capture(command, cwd):
    # Read-only tool output stays private; never echo stderr or exception text.
    value = subprocess.run(command, cwd=cwd, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, check=True, timeout=30)
    require(len(value.stdout) <= 65536)
    return value.stdout.decode().strip()


def daemon(owner):
    return observed_executor(json.loads(capture(['docker', 'info', '--format', '{{json .}}'], owner)),
                             json.loads(capture(['docker', 'version', '--format', '{{json .Server}}'], owner)))


def preflight(owner, report=None):
    require(owner.is_absolute() and owner.resolve() == owner)
    require(capture(['git', 'rev-parse', 'HEAD'], owner) == SOURCE)
    require(capture(['git', 'rev-parse', 'HEAD^{tree}'], owner) == TREE)
    require(capture(['git', 'status', '--porcelain', '--untracked-files=all'], owner) == '')
    ignored = capture(['git', 'ls-files', '--others', '--ignored', '--exclude-standard',
                       '--', 'products', 'scripts', 'src', 'tests'], owner)
    require(not any(path.endswith(('.py', '.pyc', '.pyo', '.pyd', '.so', '.sh'))
                    for path in ignored.splitlines()))
    for path, expected in INPUT_HASHES.items():
        require(hashlib.sha256((owner / path).read_bytes()).hexdigest() == expected)
    require(os.environ.get('DOCKER_HOST') == 'unix:///var/run/docker.sock')
    require(not os.environ.get('DOCKER_CONTEXT') and not os.environ.get('DOCKER_TLS_VERIFY'))
    require(stat.S_ISSOCK(Path('/var/run/docker.sock').stat().st_mode))
    observed = daemon(owner)
    if report is not None:
        report['executor'] = observed
        report['refusal'] = 'unsupported-executor'
    executor({'ID': observed['daemon_id'], 'OSType': 'linux' if observed['platform'] else None,
              'Architecture': 'amd64'},
             {'Version': observed['version'], 'GitCommit': observed['commit']})
    if report is not None:
        report['refusal'] = None
    return observed


def initial(orchestration):
    revision = capture(['git', 'rev-parse', 'HEAD'], orchestration)
    require(release.hexadecimal(revision, 40))
    require(capture(['git', 'status', '--porcelain'], orchestration) == '')
    return {'schema': 'cpk.cloudflared-retained-qualification.v1',
            'orchestration_commit': revision, 'source_commit': SOURCE, 'source_tree': TREE,
            'reference': REFERENCE, 'platform': 'linux/amd64', 'input_hashes': INPUT_HASHES,
            'stage': 'preflight', 'status': 'running', 'primary_exit': None,
            'executor': None, 'refusal': None, 'candidate_id': None, 'association_after': False,
            'controller': None,
            'controller_receipt_sha256': None, 'qualification_receipt_sha256': None,
            'qualification': None, 'cleanup': 'not-started'}


def effect(command, owner, root, name):
    with (root / (name + '.log')).open('xb') as log:
        return subprocess.run(command, cwd=owner, stdout=log, stderr=log,
                              check=False).returncode


def observe(owner):
    images = json.loads(capture(['docker', 'image', 'inspect', REFERENCE], owner))
    require(type(images) is list and len(images) == 1)
    return association(images[0])


def run(owner, root, report):
    primary = 1
    try:
        require(preflight(owner) == report['executor'])
        report['stage'] = 'pull'
        save(root, report)  # Durable fixed intent before the first acquisition.
        primary = effect(['docker', 'pull', '--platform', 'linux/amd64', REFERENCE],
                         owner, root, 'pull')
        if primary:
            return finish(root, report, primary)
        primary = 1
        require(daemon(owner) == report['executor'])
        candidate = observe(owner)
        report['candidate_id'] = candidate
        report['stage'] = 'controller-acquisition'
        save(root, report)
        controller_root = root / 'controller'
        primary = effect(['./test.sh', '--managed-connector-controller', '--receipt-dir',
                          str(controller_root)], owner, root, 'controller-acquisition')
        if primary:
            return finish(root, report, primary)
        primary = 1
        controller_path = controller_root / 'controller.json'
        controller = release.read_json(controller_path)
        release.controller_receipt(controller, controller.get('image_id'))
        require(controller['source_commit'] == SOURCE and controller['source_tree'] == TREE)
        require(controller['dockerfile_sha256'] == INPUT_HASHES['Dockerfile.test'])
        # controller_receipt admitted an exact closed key set above.
        report['controller'] = {key: controller[key] for key in (
            'schema', 'source_commit', 'source_tree', 'dockerfile_sha256',
            'image_id', 'build_exit', 'build_log_sha256')}
        report['controller_receipt_sha256'] = release.digest_file(controller_path)
        require(daemon(owner) == report['executor'] and observe(owner) == candidate)
        report['stage'] = 'qualification'
        report['cleanup'] = 'unverified'
        save(root, report)
        primary = effect(['./test.sh', '--managed-connector-candidate', '--image-id', candidate,
                          '--source', SOURCE, '--controller-image-id', controller['image_id'],
                          '--controller-receipt', str(controller_path), '--receipt-dir',
                          str(root / 'qualification')], owner, root, 'qualification')
        owner_exit = primary
        # Receipt failure cannot erase the original failed owner's exit.
        try:
            path = root / 'qualification/qualification.json'
            qualification = release.read_json(path)
            require(qualification.get('source_tree') == TREE)
            require(qualification.get('controller_id') == controller['image_id'])
            require(qualification.get('controller_receipt_sha256') == report['controller_receipt_sha256'])
            for key, source_path in [('recipe_sha256', 'products/cloudflared_connector/Dockerfile.managed'),
                                     ('witness_sha256', 'products/cloudflared_connector/tests/packaged_managed_witness.py')]:
                require(qualification.get(key) == INPUT_HASHES[source_path])
            report['qualification'] = qualification_fields(qualification, candidate)
            report['qualification_receipt_sha256'] = release.digest_file(path)
            report['cleanup'] = qualification['cleanup']
            require(daemon(owner) == report['executor'] and observe(owner) == candidate)
            report['association_after'] = True
            require_success(report['qualification'])
        except Exception:
            primary = owner_exit or 1
        if primary == 0:
            report['stage'] = 'complete'
    except Exception:
        primary = primary or 1
    return finish(root, report, primary)


def main():
    mode, owner_arg, root_arg = sys.argv[1:]
    owner, root = Path(owner_arg), Path(root_arg)
    require(root.is_absolute() and root.parent.resolve() == root.parent)
    orchestration = Path(__file__).resolve().parents[2]
    require(not root.is_relative_to(owner) and not root.is_relative_to(orchestration))
    os.umask(0o077)
    if mode == 'prepare':
        root.mkdir(mode=0o700)  # Existing attempts are never adopted or retried.
        report = initial(orchestration)
        save(root, report)
        try:
            report['executor'] = preflight(owner, report)
            report['stage'] = 'prepared'
            save(root, report)
            return 0
        except Exception:
            return finish(root, report, 1)
    require(mode == 'run' and root.resolve() == root)
    stored = release.read_json(root / 'result.json')
    template = initial(orchestration)
    require(set(stored) == set(template) and stored['stage'] == 'prepared')
    for key in ('schema', 'orchestration_commit', 'source_commit', 'source_tree',
                'reference', 'platform', 'input_hashes'):
        require(stored[key] == template[key])
    # Reconstruct the closed record; do not re-export arbitrary private state.
    observed = preflight(owner)
    require(stored['executor'] == observed)
    report = template
    report['executor'] = observed
    return run(owner, root, report)


if __name__ == '__main__':
    try:
        result = main()
    except Exception:
        result = 1
    if result:
        print('Retained qualification did not pass', file=sys.stderr)
    raise SystemExit(result)
