"""Closed hosted evidence projection. No registry/provider calls; never retries."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile

SMALL, LARGE = 65536, 1048576
REPOSITORY = 'ghcr.io/openj92/control-plane-kit-servers/cloudflared-connector'
CONTEXT = 'cpk.managed-release-context.v1'
PRODUCER_STAGES = frozenset((
    'preflight-package-read','preflight-versions-read','preflight-package-check','preflight-tag-check',
    'controller-acquisition','preflight-policy','source-archive','candidate-build','candidate-qualification',
    'candidate-check','before-push-package-read','before-push-versions-read','before-push-policy',
    'tag-candidate','push','remote-verification','published-package-read','published-versions-read',
    'published-policy','publication-record','complete',
))
FIXED = {'28.0.4':'6430e49a55babd9b8f4d08e70ecb2b68900770fe',
         '28.5.1':'f8215cc266744ef195a50a70d427c345da2acdbb'}


def require(condition):
    if not condition:
        raise ValueError('Invalid release evidence')


def keys(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value) <= set(required) | set(optional))
    return value


def text(value, maximum=512):
    require(type(value) is str and 0 < len(value) <= maximum and not re.search(r'[\x00-\x1f\x7f]',value))
    return value


def integer(value, minimum=0, maximum=2**63-1):
    require(type(value) is int and minimum <= value <= maximum)
    return value


def hexadecimal(value, length):
    require(type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is not None)
    return value


def identity(value):
    require(type(value) is str and value.startswith('sha256:'))
    hexadecimal(value[7:],64)
    return value


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def directory(path):
    """Resolve every directory component without following any symlink."""
    path=Path(path)
    require(path.is_absolute() and path.anchor=='/' and '..' not in path.parts)
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=next_fd
        return fd
    except Exception:
        os.close(fd)
        raise ValueError('Invalid release evidence') from None


def read(path, limit=SMALL):
    parent=Path(path).parent
    # A missing known phase directory means missing evidence, never success.
    if not parent.exists():
        ancestor=parent
        while not ancestor.exists():ancestor=ancestor.parent
        fd=directory(ancestor);os.close(fd)
        raise FileNotFoundError
    fd=directory(parent)
    try:
        file_fd=os.open(Path(path).name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            info=os.fstat(file_fd)
            require(stat.S_ISREG(info.st_mode) and info.st_size <= limit)
            raw=os.read(file_fd,limit+1)
            require(len(raw) <= limit and len(raw)==info.st_size)
            after=os.fstat(file_fd)
            require((info.st_size,info.st_mtime_ns,info.st_ctime_ns)==(after.st_size,after.st_mtime_ns,after.st_ctime_ns))
            return raw
        finally:os.close(file_fd)
    finally:os.close(fd)


def decode(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value);value[key]=item
        return value
    value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: require(False))
    count=0
    def bound(item,depth):
        nonlocal count
        count+=1
        require(count<=20000 and depth<=30)
        if isinstance(item,str):require(len(item)<=8192)
        elif type(item) in (int,float):require(type(item) is int and abs(item)<=2**63-1)
        elif isinstance(item,list):
            for child in item:bound(child,depth+1)
        elif isinstance(item,dict):
            for key,child in item.items():bound(key,depth+1);bound(child,depth+1)
        else:require(item is None or type(item) is bool)
    bound(value,0)
    return value


def context_value(value):
    keys(value,('schema','source_commit','source_tree','run_id','attempt'))
    require(value['schema']==CONTEXT)
    hexadecimal(value['source_commit'],40);hexadecimal(value['source_tree'],40)
    for field in ('run_id','attempt'):
        require(type(value[field]) is str and re.fullmatch(r'[1-9][0-9]{0,19}',value[field]) is not None)
    return value


def exit_code(raw):
    require(re.fullmatch(rb'(0|[1-9][0-9]{0,2})\n?',raw) is not None)
    return integer(int(raw),0,255)


def witness_value(raw):
    lines=raw.splitlines();require(len(lines)<=128)
    records=[]
    for line in lines:
        require(0<len(line)<=SMALL);records.append(decode(line))
    if not any(type(r) is dict and r.get('outcome')=='package_pass' for r in records):
        seen=set()
        for r in records:
            require(type(r) is dict)
            stage=r.get('stage')
            marker=(stage,r.get('role'))
            require(marker not in seen);seen.add(marker)
            if stage=='managed_cloudflared_controller_failure':
                keys(r,('stage','outcome','role','phase','operation','helper_mode'))
                require(r['outcome']=='unqualified' and r['role'] in ('primary','cleanup'))
                require(r['phase'] in ('setup','artifact','profile','fatal','cleanup'))
                require(r['operation'] in ('initialize','inputs','connect','owner','image_inspect','prepare_files','absence_check','create','record','start','reload','result_read','resolve_profile','stop','logs','events','kill','wait','remove','close','report'))
                require(r['helper_mode'] in (None,'contents'))
            elif stage=='managed_cloudflared_helper':
                keys(r,('stage','mode','exit_code','result'),('reason',))
                require(r['mode']=='contents');integer(r['exit_code'],1,255)
                require(r['result'] in ('invalid','unavailable','deadline_exhausted','valid_error'))
                require(('reason' in r)==(r['result']=='valid_error'))
                if 'reason' in r:require(r['reason'] in ('native_version','installed_source_coordinate','notice_source','notice_path','notice_blob','dependency_license_metadata','numeric_uid','helper_output_bound','helper_output_path','helper_output_write','helper_exception'))
            elif stage=='managed_cloudflared_controller':
                keys(r,('stage','outcome','reason','states'))
                require(r['outcome']=='unqualified');text(r['reason'])
                require(type(r['states']) is list and len(r['states'])<=100)
                ids=set()
                for state in r['states']:
                    keys(state,('id','status'),('exit_code','pid'))
                    hexadecimal(state['id'],64);require(state['id'] not in ids);ids.add(state['id'])
                    require(state['status'] in ('created','running','paused','restarting','removing','exited','dead','observation_unavailable'))
                    if state['status']=='observation_unavailable':require(set(state)=={'id','status'})
                    else:integer(state['exit_code']);integer(state['pid'])
            elif stage=='stop_profile_inputs':
                keys(r,('stage','container_id','engine_id','engine_version','engine_commit','platform','docker_sdk','configured_signal','configured_timeout'))
                hexadecimal(r['container_id'],64)
                for field in ('engine_id','engine_version','engine_commit','platform','docker_sdk','configured_signal'):text(r[field])
                if r['configured_timeout'] is not None:integer(r['configured_timeout'])
            else:require(False)
        return None
    # A successful owner emits precisely these two records. Partial logs remain
    # unverified; no recovery or reason text is projected from failed witnesses.
    require(len(records)==2)
    p,w=records
    keys(p,('stage','container_id','engine_id','engine_version','engine_commit','platform','docker_sdk','configured_signal','configured_timeout'))
    keys(w,('stage','outcome','live_qualification','profile_container_id','docker_sdk','engine_id','engine_version','engine_commit',
            'stop_timeout','configured_stop_timeout','reviewed_engine_source','timeout_origin','stop_signal',
            'term_time_ns','kill_time_ns','die_time_ns','native_version','installed'))
    require(p['stage']=='stop_profile_inputs' and w['stage']=='managed_cloudflared_controller' and
            w['outcome']=='package_pass' and w['live_qualification']=='pending')
    hexadecimal(p['container_id'],64);require(p['container_id']==w['profile_container_id'])
    text(p['engine_id']);require(p['engine_id']==w['engine_id'])
    for field in ('engine_version','engine_commit','docker_sdk'):require(p[field]==w[field])
    require(re.fullmatch(r'[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}(?:[-+.][A-Za-z0-9.-]{1,32})?',text(w['engine_version'],64)) is not None)
    require(re.fullmatch(r'[0-9a-f]{7,40}',text(w['engine_commit'],40)) is not None)
    require(p['platform']=='linux' and w['docker_sdk']=='7.2.0' and p['configured_signal']==w['stop_signal']=='SIGTERM')
    require(p['configured_timeout']==w['configured_stop_timeout'])
    require(integer(w['stop_timeout'])==10)
    if w['configured_stop_timeout'] is None:
        source=FIXED.get(w['engine_version'])
        require(source is not None and source.startswith(w['engine_commit']) and
                w['reviewed_engine_source']==source and w['timeout_origin']=='engine_fixed_default')
    else:
        require(integer(w['configured_stop_timeout'])==10 and w['timeout_origin']=='container' and w['reviewed_engine_source'] is None)
    term,kill,die=[integer(w[f]) for f in ('term_time_ns','kill_time_ns','die_time_ns')]
    require(term<kill<=die and 9000000000<=kill-term<=11000000000 and w['native_version']=='2026.6.1')
    require(type(w['installed']) is dict and len(w['installed'])<=500)
    for name,version in w['installed'].items():text(name,200);text(version,200)
    return dict(engine_version=w['engine_version'],engine_commit=w['engine_commit'],reviewed_engine_source=w['reviewed_engine_source'],
        docker_sdk=w['docker_sdk'],platform='linux',configured_timeout=w['configured_stop_timeout'],effective_timeout=10,
        timeout_origin=w['timeout_origin'],signal='SIGTERM',term_to_kill_ns=kill-term,kill_to_die_ns=die-kill,
        owner_witness='cpk.managed-cloudflared-packaged-witness.v1')


def project(receipts, source_root, context, producer_exit):
    try:
        context=context_value(context)
        if producer_exit is not None:integer(producer_exit,0,255)
        root=Path(receipts);source_root=Path(source_root)
        fd=directory(root if root.exists() else root.parent);os.close(fd)
        fd=directory(source_root);os.close(fd)
        source=dict(commit=context['source_commit'],tree=context['source_tree'],
            managed_recipe_sha256=sha(read(source_root/'products/cloudflared_connector/Dockerfile.managed')),
            controller_recipe_sha256=sha(read(source_root/'Dockerfile.test')),
            witness_sha256=sha(read(source_root/'products/cloudflared_connector/tests/packaged_managed_witness.py')))
    except Exception:
        raise ValueError('Invalid release evidence') from None
    tag='managed-'+source['commit']
    result=dict(schema='cpk.cloudflared-managed-evidence.v2',source=source,
        workflow=dict(run_id=context['run_id'],attempt=context['attempt']),
        outcomes=dict(producer_exit=producer_exit,push_command_exit=None,remote_publication='unknown',qualification='unknown',
            cleanup='unverified',candidate_retained_before_runner_disposal=None,projection='incomplete',retention='pending-upload'),
        artifacts=dict(candidate_id=None,controller_id=None,intended_tag=tag,reference=None,index_digest=None,platform_manifest=None,config_digest=None),
        controller_receipt_sha256=None,qualification_receipt_sha256=None,stop=None,native_version=None,producer_diagnostic=None,
        package_checks=dict(preflight='unknown',before_push='unknown',published='unknown'),failure='missing-evidence')
    invalid=False
    def attempt(fn):
        nonlocal invalid
        try:return fn()
        except FileNotFoundError:return None
        except Exception:invalid=True;return None
    def js(name,limit=SMALL):return decode(read(root/name,limit))
    def producer_diagnostic():
        value=js('producer-diagnostic.json',1024)
        keys(value,('schema','source_commit','stage','exit_code'))
        require(value['schema']=='cpk.cloudflared-managed-producer-diagnostic.v1' and value['source_commit']==source['commit'])
        require(type(value['stage']) is str and value['stage'] in PRODUCER_STAGES)
        code=integer(value['exit_code'],0,255)
        require((value['stage']=='complete')==(code==0))
        require(producer_exit is None or producer_exit==code)
        result['producer_diagnostic']=dict(stage=value['stage'],exit_code=code)
    attempt(producer_diagnostic)
    push=attempt(lambda:exit_code(read(root/'push.exit',8)))
    result['outcomes']['push_command_exit']=push
    def controller():
        raw=read(root/'controller/controller.json');c=decode(raw)
        keys(c,('schema','source_commit','source_tree','dockerfile_sha256','image_id','build_exit','build_log_sha256'))
        require(c['schema']=='cpk.cloudflared-controller-acquisition.v1' and c['source_commit']==source['commit'] and
                c['source_tree']==source['tree'] and c['dockerfile_sha256']==source['controller_recipe_sha256'] and integer(c['build_exit'])==0)
        identity(c['image_id']);hexadecimal(c['build_log_sha256'],64)
        result['artifacts']['controller_id']=c['image_id'];result['controller_receipt_sha256']=sha(raw)
        return c,raw
    c=attempt(controller)
    def candidate():
        raw=read(root/'candidate.id',72).decode('ascii')
        value=identity(raw.removesuffix('\n'));require(raw in (value,value+'\n'))
        result['artifacts']['candidate_id']=value;return value
    candidate_id=attempt(candidate)
    def qualification():
        raw=read(root/'qualification/qualification.json');q=decode(raw)
        keys(q,('schema','candidate_id','source_commit','status','cleanup','candidate_retained','run','controller_id','source_tree',
                'recipe_sha256','witness_sha256','controller_receipt_sha256'),('platform','created_containers','witness_log_sha256'))
        require(q['schema']=='cpk.cloudflared-managed-qualification.v1' and q['source_commit']==source['commit'] and
                q['source_tree']==source['tree'] and q['recipe_sha256']==source['managed_recipe_sha256'] and q['witness_sha256']==source['witness_sha256'])
        require(c is not None and candidate_id is not None and q['candidate_id']==candidate_id and q['controller_id']==c[0]['image_id'])
        require(read(root/'qualification/controller.json')==c[1] and q['controller_receipt_sha256']==sha(c[1]))
        text(q['run']);require(q['status'] in ('running','pass','fail') and q['cleanup'] in ('verified','unverified') and type(q['candidate_retained']) is bool)
        if 'created_containers' in q:
            require(type(q['created_containers']) is list and len(q['created_containers'])<=100)
            for item in q['created_containers']:hexadecimal(item,64)
            require(len(set(q['created_containers']))==len(q['created_containers']))
        if 'platform' in q:require(q['platform']=='linux/amd64')
        if 'witness_log_sha256' in q:hexadecimal(q['witness_log_sha256'],64)
        result['qualification_receipt_sha256']=sha(raw)
        result['outcomes']['cleanup']=q['cleanup'];result['outcomes']['candidate_retained_before_runner_disposal']=q['candidate_retained']
        if q['status']=='fail':result['outcomes']['qualification']='fail'
        return q,raw
    q=attempt(qualification)
    def stop():
        require(q is not None)
        raw=read(root/'qualification/witness.log',LARGE)
        require(q[0].get('witness_log_sha256')==sha(raw))
        value=witness_value(raw)
        if value is None:
            require(q[0]['status']!='pass')
            return None
        result['stop']=value;result['native_version']='2026.6.1'
        if q[0]['status']=='pass' and q[0]['cleanup']=='verified' and q[0]['candidate_retained'] and q[0].get('platform')=='linux/amd64':
            result['outcomes']['qualification']='pass'
        return value
    w=attempt(stop) if q is not None else None
    packages={}
    for phase in ('preflight','before-push','published'):
        def package(phase=phase):
            p=js(phase+'/validated.json');keys(p,('package_id','visibility','tag','digest','version_id'))
            integer(p['package_id'],1);require(p['visibility']=='private' and p['tag']==tag)
            if phase=='published':identity(p['digest']);integer(p['version_id'],1)
            else:require(p['digest'] is None and p['version_id'] is None)
            result['package_checks'][phase.replace('-','_')]='private-matching-digest' if phase=='published' else 'private-unused-tag'
            return p
        packages[phase]=attempt(package)
    def publication():
        pub=js('publication.json')
        keys(pub,('schema','reference','candidate_id','source_commit','platform_manifest','config_digest','qualification_sha256','visibility','status'))
        require(pub['schema']=='cpk.cloudflared-managed-publication.v1' and pub['source_commit']==source['commit'] and
                candidate_id is not None and pub['candidate_id']==candidate_id and c is not None and q is not None and w is not None)
        require(result['outcomes']['qualification']=='pass' and pub['qualification_sha256']==sha(q[1]) and pub['visibility']=='private' and pub['status']=='verified')
        require(all(packages.values()) and len({p['package_id'] for p in packages.values()})==1)
        require(exit_code(read(root/'build.exit',8))==0 and exit_code(read(root/'qualification/controller.exit',8))==0)
        meta=js('build-metadata.json',LARGE)
        keys(meta,('containerimage.digest','containerimage.config.digest'),('buildx.build.ref','containerimage.descriptor','buildx.build.provenance','buildx.build.warnings','containerimage.buildinfo','containerimage.buildinfo.digest'))
        index_digest=identity(meta['containerimage.digest']);config=identity(meta['containerimage.config.digest'])
        if 'containerimage.descriptor' in meta:require(meta['containerimage.descriptor']['digest']==index_digest)
        raw=read(root/'remote-index.json',LARGE);require('sha256:'+sha(raw)==index_digest)
        index=decode(raw);manifest_keys=('schemaVersion','mediaType','manifests','config','layers','annotations','artifactType','subject')
        keys(index,('schemaVersion',),manifest_keys);require(type(index['schemaVersion']) is int and index['schemaVersion']==2)
        platform_digest=index_digest
        if 'manifests' in index:
            require(type(index['manifests']) is list)
            selected=[m for m in index['manifests'] if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64']
            require(len(selected)==1);platform_digest=identity(selected[0]['digest'])
        platform_raw=read(root/'remote-platform.json',LARGE);require('sha256:'+sha(platform_raw)==platform_digest)
        manifest=decode(platform_raw);keys(manifest,('schemaVersion','config','layers'),manifest_keys)
        require(type(manifest['schemaVersion']) is int and manifest['schemaVersion']==2 and manifest['config']['digest']==config)
        def descriptor(v):
            keys(v,('digest',),('mediaType','size','urls','annotations','platform','artifactType','data'))
            identity(v['digest'])
        descriptor(manifest['config'])
        require(type(manifest['layers']) is list)
        for item in manifest['layers']:descriptor(item)
        for item in index.get('manifests',[]):descriptor(item)
        remote=js('remote-config.json',LARGE)
        keys(remote,('os','architecture','config'),('created','author','variant','os.version','os.features','rootfs','history','container','docker_version','container_config'))
        keys(remote['config'],('Labels',),('User','ExposedPorts','Env','Entrypoint','Cmd','Volumes','WorkingDir','StopSignal','ArgsEscaped','Healthcheck','OnBuild','Shell','Hostname','Domainname','AttachStdin','AttachStdout','AttachStderr','Tty','OpenStdin','StdinOnce','NetworkDisabled','MacAddress','StopTimeout'))
        require(remote['os']=='linux' and remote['architecture']=='amd64' and remote['config']['Labels']['org.opencontainers.image.revision']==source['commit'])
        require(pub['reference']==REPOSITORY+'@'+index_digest and pub['platform_manifest']==platform_digest and pub['config_digest']==config and packages['published']['digest']==index_digest)
        result['artifacts'].update(reference=pub['reference'],index_digest=index_digest,platform_manifest=platform_digest,config_digest=config)
        result['outcomes']['remote_publication']='verified'
        return True
    published=attempt(publication)
    result['outcomes']['projection']='invalid' if invalid else 'complete' if published else 'incomplete'
    result['failure']='invalid-evidence' if invalid else None if published else 'missing-evidence'
    require(len(json.dumps(result).encode())<=SMALL)
    return result


def clean_context(source_root,run_id,attempt):
    def git(*args):
        return subprocess.run(['git',*args],cwd=source_root,check=True,capture_output=True,text=True).stdout.strip()
    require(not git('status','--porcelain'))
    return context_value(dict(schema=CONTEXT,source_commit=git('rev-parse','HEAD'),source_tree=git('rev-parse','HEAD^{tree}'),run_id=run_id,attempt=attempt))


def prepare(source_root,runner_temp,run_id,attempt):
    context=clean_context(source_root,run_id,attempt)
    fd=directory(source_root);os.close(fd)
    fd=directory(runner_temp);os.close(fd)
    require(not Path(runner_temp).is_relative_to(Path(source_root)))
    path=Path(tempfile.mkdtemp(prefix='cpk-managed-release-',dir=runner_temp))
    os.chmod(path,0o700)
    with (path/'context.json').open('x') as stream:json.dump(context,stream)
    return path


def run_attempt(attempt,source_root):
    attempt=Path(attempt)
    try:
        context=context_value(decode(read(attempt/'context.json')))
        require(clean_context(source_root,context['run_id'],context['attempt'])==context)
        # Exclusive local stream creation prevents an accidental same-attempt retry.
        fd=os.open(attempt/'producer.log',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            process=subprocess.run(['sh','scripts/publish_product_image.sh','cloudflared-connector-managed','managed-'+context['source_commit']],
                cwd=source_root,env=dict(os.environ,CPK_MANAGED_RELEASE_RECEIPTS=str(attempt/'receipts')),
                stdout=stream,stderr=subprocess.STDOUT)
        code=process.returncode if process.returncode>=0 else min(255,128-process.returncode)
        with (attempt/'producer.exit').open('x') as stream:stream.write(str(code)+'\n')
        return code
    except Exception:
        raise ValueError('Invalid release evidence') from None


def export(receipts,source_root,context,producer_exit,destination,*,invalid_exit=False):
    value=project(receipts,source_root,context,producer_exit)
    if invalid_exit:
        value['outcomes']['projection']='invalid'
        value['failure']='invalid-evidence'
    destination=Path(destination)
    try:
        fd=directory(destination.parent);os.close(fd)
        destination.mkdir(mode=0o700)
        payload=(json.dumps(value,sort_keys=True)+'\n').encode();require(len(payload)<=SMALL)
        path=destination/'managed-release-evidence.json'
        temporary=destination/'.evidence.tmp'
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
        os.rename(temporary,path)
        return value
    except Exception:
        raise ValueError('Invalid release evidence') from None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('mode',choices=('prepare','run','export'))
    parser.add_argument('--attempt')
    args=parser.parse_args()
    source=Path(__file__).resolve().parents[2]
    try:
        if args.mode=='prepare':
            expected=clean_context(source,os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'])
            require(os.environ['IMAGE_TAG']=='managed-'+expected['source_commit'])
            path=prepare(source,os.environ['RUNNER_TEMP'],os.environ['GITHUB_RUN_ID'],os.environ['GITHUB_RUN_ATTEMPT'])
            with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('attempt='+str(path)+'\n')
            return 0
        path=Path(args.attempt)
        if args.mode=='run':return run_attempt(path,source)
        context=context_value(decode(read(path/'context.json')))
        require(clean_context(source,context['run_id'],context['attempt'])==context)
        invalid_exit=False
        try:raw=read(path/'producer.exit',SMALL)
        except FileNotFoundError:code=None
        else:
            try:code=exit_code(raw)
            except ValueError:code=None;invalid_exit=True
        value=export(path/'receipts',source,context,code,path/'public',invalid_exit=invalid_exit)
        return 0 if value['outcomes']['projection']=='complete' else 1
    except Exception:
        print('Managed release evidence unavailable',file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
