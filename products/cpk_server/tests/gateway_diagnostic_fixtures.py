"""Synthetic public packet and recording owner seams; never live authority."""
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import control_plane_kit_core as core
from control_plane_kit_core.identity import AuthenticatedPrincipal, PrincipalIdentity, PrincipalKind, WorkspaceGrant
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.public_ingress import NamedPublicIngress, IngressAuthorityReference, PublicIngressTarget
from cpk_http_host_fixtures import fixture
from health_receiver_join_fixtures import gateway_self_world, document


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def packet_world():
    value = gateway_self_world()
    other = fixture("transit")
    value.trust = replace(value.trust, public_keys=other.config.health_keys.public_keys)
    value.artifacts["transit"] = value.transit.gateway_health_transit_configuration_artifact(value.trust)
    value.contract = value.relay.gateway_health_source_runtime_contract(
        value.artifacts["transit"], value.artifacts["targets"], value.artifacts["control"])
    value.document = document("diagnostic-gateway", value.contract)
    artifacts = {name: item.content.encode() for name, item in value.artifacts.items()}
    artifacts["product"] = value.document.content
    request = core.NodeHealthReadRequest(value.config.target, value.config.runtime_id,
        core.NodeHealthReadKind.READINESS, value.config.declaration.identity(), "diagnostic-request")
    common = dict(canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
        target=request.target, runtime_id=request.runtime_id, kind=request.kind,
        declaration_identity=request.declaration_identity, request_id=request.request_id,
        request_digest=request.canonical_digest(), issued_at=100, not_before=101, expires_at=200)
    transit = core.DelegatedGatewayNodeHealthReadTransitGrant(
        profile=core.DelegatedGatewayNodeHealthReadTransitGrantProfile.V1,
        purpose=value.trust.purpose, issuer=value.trust.issuer, key_id=value.trust.public_keys[0].key_id,
        gateway_node_id=request.target.node_id, attempt_id="diagnostic-attempt", jti="transit-jti", **common)
    workload = core.DelegatedWorkloadNodeHealthReadGrant(
        profile=core.DelegatedWorkloadNodeHealthReadGrantProfile.V1,
        purpose=value.config.health_keys.purpose, issuer=value.config.health_issuer,
        key_id=value.config.health_keys.public_keys[0].key_id,
        audience=core.workload_node_control_audience(request.target), jti="workload-jti", **common)
    ingress = NamedPublicIngress("management", IngressAuthorityReference("diagnostic-authority"),
        PublicIngressTarget("gateway-a", "control"), "connector-a", "diagnostic.example.invalid")
    packet = dict(profile="gateway-self-health-diagnostic.v1", attempt_id="diagnostic-attempt",
        request=request.descriptor(), ingress=ingress.descriptor(), target_id=value.binding.target_id,
        transit_socket="control", source_commit="7"*40, image_digest="sha256:"+"8"*64,
        resource_plan="diagnostic-plan", artifacts={name:hashlib.sha256(raw).hexdigest()
            for name,raw in artifacts.items()}, transit_grant=transit.descriptor(), workload_grant=workload.descriptor(),
        keys=[dict(registration_id="key-"+family, key_id=key.key_id,
            fingerprint=key.fingerprint_sha256, private_reference="secret://provider-a/"+family,
            reference_registration_id="reference-"+family, provider_registration_id="provider-a",
            endpoint_reference="provider-a", credential_reference="secret://bootstrap/provider-a")
            for family,key in (("transit",value.trust.public_keys[0]),("workload",value.config.health_keys.public_keys[0]))])
    principal = AuthenticatedPrincipal(PrincipalIdentity("test-issuer","operator-a",PrincipalKind.OPERATOR),
        (WorkspaceGrant("workspace-a",(PolicyScope.SECRET_PROVIDER_USE,)),))
    return SimpleNamespace(value=value, artifacts=artifacts, packet=packet, raw=encode(packet),
        request=request, transit=transit, workload=workload, principal=principal)


def recording_authority(api, selected, world, *, existing=False, exit_error=False, fail_second=False):
    from control_plane_kit_core.secrets import SecretReference, SecretProviderId, SecretProviderEndpointReference, SecretUseIntent
    from control_plane_kit_operations.secret_providers import RegisteredSecretProvider, RegisteredSecretReference, SecretProviderKind
    from control_plane_kit_operations.delegation_signing_keys import RegisteredDelegationSigningKey, RegisteredDelegationSigningKeyStatus
    from control_plane_kit_servers_cpk_server.authentication import StaticDevelopmentMultiCredentialVerifier, StaticDevelopmentPrincipalCredential
    events, added = [], []
    intents = (SecretUseIntent.GATEWAY_NODE_HEALTH_READ_TRANSIT_SIGNING_KEY,
               SecretUseIntent.WORKLOAD_NODE_HEALTH_READ_SIGNING_KEY)
    stamp = "2026-09-23T00:00:00Z"
    provider = RegisteredSecretProvider("provider-a","workspace-a",SecretProviderId("provider-a"),
        SecretProviderKind.CONTROL_PLANE_KIT_SECRETS,"Diagnostic fixture",SecretProviderEndpointReference("provider-a"),
        SecretReference("secret://bootstrap/provider-a"),(SecretReference("secret://provider-a"),),intents,"fixture",stamp)
    refs = tuple(RegisteredSecretReference("reference-"+family,"workspace-a",
        SecretReference("secret://provider-a/"+family),"provider-a",(intent,),"fixture",stamp)
        for family,intent in zip(("transit","workload"),intents))
    keys = list(RegisteredDelegationSigningKey("key-"+family,"workspace-a",purpose,issuer,key,ref.reference,
        "fixture",stamp,status=RegisteredDelegationSigningKeyStatus.ACTIVE,activated_by="fixture",activated_at=stamp)
        for family,purpose,issuer,key,ref in zip(("transit","workload"),
            (world.value.trust.purpose,world.value.config.health_keys.purpose),
            (world.value.trust.issuer,world.value.config.health_issuer),
            (world.value.trust.public_keys[0],world.value.config.health_keys.public_keys[0]),refs))
    providers = [provider]
    references = list(refs)
    hooks = SimpleNamespace(on_exit=lambda:None)
    class Uses:
        def lock_correlation(self,workspace,correlation): events.append(("lock",correlation))
        def for_correlation(self,workspace,correlation):
            events.append(("read",correlation))
            return object() if existing is True or (existing and correlation in existing) else None
        def add(self,value):
            if fail_second and added: raise ValueError("provider-private-canary")
            added.append(value)
            events.append(("add",value.correlation_id))
    class Uow:
        def __init__(self):
            self.stores = SimpleNamespace(secret_use_authorizations=Uses(),
                delegation_signing_keys=SimpleNamespace(require_unambiguous_active=lambda workspace,purpose:
                    next(key for key in keys if key.purpose is purpose)),
                secret_references=SimpleNamespace(get_active_for_update=lambda workspace,reference:
                    next(ref for ref in references if ref.reference==reference)),
                secret_providers=SimpleNamespace(require_active_registration_for_update=lambda workspace,registration:providers[0]))
        def __enter__(self): events.append(("enter",)); return self
        def commit(self): events.append(("commit-request",))
        def __exit__(self,*args):
            events.append(("exit",args[0]))
            if exit_error: raise RuntimeError("database-private-canary")
            hooks.on_exit()
    approval = dict(packet_digest=selected.packet_digest,issuer="test-issuer",subject="operator-a",
        workspace_id="workspace-a",attempt_id="diagnostic-attempt",database_identity="existing-db",expires_at=210,
        reference="reviewed-approval")
    authority = api.DiagnosticAuthority(
        verifier=StaticDevelopmentMultiCredentialVerifier((StaticDevelopmentPrincipalCredential(b"test-token",world.principal),)),
        credential=b"test-token",approval_reader=lambda:dict(approval),workspace_id="workspace-a",database_identity="existing-db",
        unit_of_work=Uow,resolver=None)
    return SimpleNamespace(authority=authority,events=events,added=added,approval=approval,keys=keys,
        providers=providers,references=references,hooks=hooks)
