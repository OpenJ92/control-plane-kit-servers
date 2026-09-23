"""Protected invocation setup; path provenance is an operator approval boundary."""
import os
from pathlib import Path
import stat

from control_plane_kit_core.identity import AuthenticatedPrincipal,PrincipalIdentity,PrincipalKind,WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.secrets import SecretProviderEndpointReference,SecretReference
from .authentication import StaticDevelopmentMultiCredentialVerifier,StaticDevelopmentPrincipalCredential
from ._gateway_diagnostic_input import bounded_json,closed,reference


def read_file(path,maximum,*,protected=False):
    path=Path(path)
    if not path.is_absolute(): raise ValueError
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size>maximum: raise ValueError
        if protected and (info.st_uid not in (0,os.geteuid()) or info.st_mode & 0o077): raise ValueError
        with os.fdopen(descriptor,"rb",closefd=False) as stream: raw=stream.read(maximum+1)
        if not 1<=len(raw)<=maximum: raise ValueError
        return raw
    finally: os.close(descriptor)


def read_authority(path):
    # Only this run-mode boundary loads protected setup. The candidate packet
    # supplies no principal, database URL, credential path or bootstrap map.
    from control_plane_kit_operations.postgres import PostgresUnitOfWork
    from control_plane_kit_interpreters.secret_provider.bootstrap import SecretProviderBootstrapRegistry
    from control_plane_kit_interpreters.secret_provider.resolver import ControlPlaneKitSecretsResolver
    from .gateway_self_health_diagnostic import DiagnosticAuthority
    import psycopg
    setup=closed(bounded_json(read_file(path,65536,protected=True)),{
        "workspace_id","database_identity","database_dsn_file","operator_credential_file",
        "principal_bindings_file","approval_file","secret_endpoints","secret_credentials"})
    for name in ("workspace_id","database_identity"): reference(setup[name])
    bindings=bounded_json(read_file(setup["principal_bindings_file"],65536,protected=True))
    if type(bindings) is not list or not 1<=len(bindings)<=16: raise ValueError
    credentials=[]
    for binding in bindings:
        closed(binding,{"issuer","subject","kind","workspace_grants","credential_file"})
        if type(binding["workspace_grants"]) is not list or len(binding["workspace_grants"])>64: raise ValueError
        grants=[]
        for grant in binding["workspace_grants"]:
            closed(grant,{"workspace_id","scopes"})
            if type(grant["scopes"]) is not list: raise ValueError
            grants.append(WorkspaceGrant(grant["workspace_id"],tuple(PolicyScope(scope) for scope in grant["scopes"])))
        principal=AuthenticatedPrincipal(PrincipalIdentity(binding["issuer"],binding["subject"],PrincipalKind(binding["kind"])),tuple(grants))
        credentials.append(StaticDevelopmentPrincipalCredential(read_file(binding["credential_file"],4096,protected=True),principal))
    verifier=StaticDevelopmentMultiCredentialVerifier(tuple(credentials))
    credential=read_file(setup["operator_credential_file"],4096,protected=True)
    dsn=read_file(setup["database_dsn_file"],4096,protected=True).decode("utf-8")
    if type(setup["secret_endpoints"]) is not dict or type(setup["secret_credentials"]) is not dict: raise ValueError
    if not 1<=len(setup["secret_endpoints"])<=64 or not 1<=len(setup["secret_credentials"])<=64: raise ValueError
    registry=SecretProviderBootstrapRegistry(
        {SecretProviderEndpointReference(key):value for key,value in setup["secret_endpoints"].items()},
        {SecretReference(key):Path(value) for key,value in setup["secret_credentials"].items()})
    approval_path=Path(setup["approval_file"])
    return DiagnosticAuthority(verifier,credential,
        lambda:bounded_json(read_file(approval_path,16384,protected=True)),setup["workspace_id"],setup["database_identity"],
        lambda:PostgresUnitOfWork(lambda:psycopg.connect(dsn)),ControlPlaneKitSecretsResolver(registry))
