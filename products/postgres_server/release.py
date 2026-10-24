"""Closed managed PostgreSQL artifact selection; no effects or credentials."""
import json
from pathlib import Path
import re
import sys

REPOSITORY='ghcr.io/openj92/control-plane-kit-servers/postgres-server'
SOURCE_REPOSITORY='OpenJ92/control-plane-kit-servers'


def require(value):
    if not value:raise ValueError('Managed PostgreSQL artifact is invalid')


def hex_value(value,length):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) is not None


def image_id(value):
    return type(value) is str and value.startswith('sha256:') and hex_value(value[7:],64)


def publication_destination(owner,package,tag,source):
    require(owner=='openj92' and package=='control-plane-kit-servers')
    require(hex_value(source,40) and tag=='managed-'+source)
    return REPOSITORY+':'+tag


def published_reference(reference):
    require(type(reference) is str and reference.startswith(REPOSITORY+'@'))
    require(image_id(reference[len(REPOSITORY)+1:]))
    return reference


def repository_visibility(repository):
    require(type(repository) is dict and repository.get('full_name')==SOURCE_REPOSITORY
            and type(repository.get('id')) is int and repository['id']>0
            and repository.get('visibility') in ('public','private')
            and type(repository.get('private')) is bool
            and repository['private']==(repository['visibility']=='private'))
    return repository['visibility']


def package_check(package,pages,source,reference=None,*,repository):
    publication_destination('openj92','control-plane-kit-servers','managed-'+source,source)
    visibility=repository_visibility(repository)
    require(type(package) is dict and package.get('name')=='control-plane-kit-servers/postgres-server'
            and package.get('package_type')=='container' and package.get('visibility')==visibility
            and type(package.get('id')) is int and package['id']>0)
    associated=package.get('repository')
    require(type(associated) is dict and associated.get('full_name')==SOURCE_REPOSITORY
            and type(associated.get('id')) is int and associated['id']==repository['id'])
    require(type(pages) is list and len(pages)>0)
    found=[];ids=set()
    for page in pages:
        require(type(page) is list)
        for version in page:
            require(type(version) is dict and type(version.get('id')) is int and version['id']>0
                    and version['id'] not in ids and image_id(version.get('name')))
            ids.add(version['id'])
            metadata=version.get('metadata');require(type(metadata) is dict)
            container=metadata.get('container');require(type(container) is dict)
            tags=container.get('tags');require(type(tags) is list and all(type(t) is str for t in tags))
            require(len(tags)==len(set(tags)))
            if 'managed-'+source in tags:found.append(version)
    if reference is None:require(not found)
    else:
        published_reference(reference)
        require(len(found)==1 and found[0]['name']==reference.split('@')[1])


def first_publication_check(raw,exit_status):
    """Admit only the exact package GET's 404 observation, not proof of absence."""
    require(exit_status=='1' and type(raw) is bytes and len(raw)<=65536)
    header,separator,body=raw.replace(b'\r\n',b'\n').partition(b'\n\n')
    require(separator and re.fullmatch(rb'HTTP/(?:1\.[01]|2(?:\.0)?) 404(?: Not Found)?',header.split(b'\n')[0]))
    require(all(b':' in line for line in header.split(b'\n')[1:]))
    value=decode_json(body)
    require(type(value) is dict and value.get('status')=='404'
            and value.get('message') in ('Not Found','Package not found.'))


def first_published_package(package,pages,source,reference,*,repository):
    package_check(package,pages,source,reference,repository=repository)


def published_image(attrs,reference,source,recipe):
    published_reference(reference)
    require(hex_value(source,40) and hex_value(recipe,64) and type(attrs) is dict)
    require(image_id(attrs.get('Id')) and type(attrs.get('RepoDigests')) is list
            and reference in attrs['RepoDigests'] and attrs.get('Os')=='linux' and attrs.get('Architecture')=='amd64')
    config=attrs.get('Config');require(type(config) is dict)
    require(config.get('User')=='70:70' and config.get('Entrypoint') in (None,[])
            and config.get('Cmd')==['python3','-m','control_plane_kit_servers_postgres_server.process'])
    labels=config.get('Labels');require(type(labels) is dict)
    require(labels.get('org.opencontainers.image.revision')==source
            and labels.get('org.openj92.cpk.recipe.sha256')==recipe)
    return attrs['Id']


def decode_json(raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value);value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=unique)


def bounded_bytes(path,limit):
    with Path(path).open('rb') as stream:raw=stream.read(limit+1)
    require(len(raw)<=limit)
    return raw


def bounded_json(path,limit):
    return decode_json(bounded_bytes(path,limit))


def main():
    mode,*args=sys.argv[1:]
    if mode=='destination':print(publication_destination(*args))
    elif mode=='repository':
        root,=args
        repository=bounded_json(Path(root)/'repository.json',65536)
        visibility=repository_visibility(repository)
        print(str(repository['id'])+':'+visibility)
    elif mode=='first-preflight':
        root,status=args
        first_publication_check(bounded_bytes(Path(root)/'package.response',65536),status)
    elif mode in ('package','first-published'):
        root,source,*reference=args
        require(len(reference)<=1)
        check=first_published_package if mode=='first-published' else package_check
        check(bounded_json(Path(root)/'package.json',65536),
              bounded_json(Path(root)/'versions.json',4194304),source,*reference,
              repository=bounded_json(Path(root)/'repository.json',65536))
    else:require(False)


if __name__=='__main__':
    try:main()
    except Exception:
        print('Managed PostgreSQL artifact is invalid',file=sys.stderr)
        raise SystemExit(1)
