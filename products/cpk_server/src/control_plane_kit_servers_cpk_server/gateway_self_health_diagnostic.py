"""Operator diagnostic composition; never a deployment or authority shortcut.

Trusted bootstrap and approval provenance belong to the reviewed invocation.
Existing Operations owns authorization truth; its transaction exits before I/O.
"""
import argparse
import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from control_plane_kit_core.delegation_keys import DelegationKeyPurpose
from control_plane_kit_core.identity import PrincipalKind
from control_plane_kit_core.policies import PolicyScope
from control_plane_kit_core.secrets import SecretUseIntent
from control_plane_kit_operations.cpk_server import RouteAuthorizationPolicy
from control_plane_kit_operations.secret_providers import authorize_secret_use_in_unit_of_work, secret_resolution_grant_for, AuthorizeSecretUse
from control_plane_kit_interpreters.probes.health_signing import Ed25519HealthCredentialPairSigner, HealthSigningKey
from control_plane_kit_interpreters.probes.health_transport import SignedGatewayHealthClient
from .authentication import authenticate_bearer_credential
from ._gateway_diagnostic_input import DiagnosticInputError, prepare_packet, closed, reference


@dataclass(frozen=True,repr=False)
class DiagnosticAuthority:
    verifier: object
    credential: bytes
    approval_reader: object
    workspace_id: str
    database_identity: str
    unit_of_work: object
    resolver: object


class _PriorAttempt(ValueError): pass


def _now(clock):
    now=clock()
    if type(now) is not int or not 0 <= now <= 9007199254740991: raise ValueError
    return now


def _approval(selected,authority,context,clock):
    approval=closed(authority.approval_reader(),{"packet_digest","issuer","subject","workspace_id",
        "attempt_id","database_identity","expires_at","reference"})
    expected=dict(packet_digest=selected.packet_digest,issuer=context.principal.identity.issuer,
        subject=context.principal.identity.subject_id,workspace_id=selected.workspace_id,
        attempt_id=selected.context.attempt_id,database_identity=authority.database_identity)
    if (any(approval[name]!=value for name,value in expected.items())
            or authority.workspace_id!=selected.workspace_id): raise ValueError
    reference(approval["reference"])
    expiry=approval["expires_at"]
    now=_now(clock)
    if type(expiry) is not int or not now < expiry <= 9007199254740991: raise ValueError
    for grant in (selected.transit_grant,selected.workload_grant):
        if not grant.issued_at <= now or not grant.not_before <= now < grant.expires_at <= expiry: raise ValueError
    return approval


async def run_diagnostic(selected,authority,*,clock):
    evidence=dict(packet_digest=selected.packet_digest,attempt_id=selected.context.attempt_id,
        request_digest=selected.context.request.canonical_digest().value)
    try:
        principal=authenticate_bearer_credential(
            {"Authorization":"Bearer "+authority.credential.decode("ascii")},authority.verifier)
        context=principal.command_context(selected.workspace_id)
        RouteAuthorizationPolicy(required_scopes=(PolicyScope.SECRET_PROVIDER_USE,),
            principal_kinds=(PrincipalKind.OPERATOR,)).authorize(context)
        approval=_approval(selected,authority,context,clock)
    except Exception:
        return dict(status="approval-authentication-denied",**evidence)
    evidence.update(approval_reference=approval["reference"],actor=context.principal.identity.subject_id)
    commit_requested=False
    projected=[]
    current_keys=[]
    try:
        with authority.unit_of_work() as uow:
            store=uow.stores.secret_use_authorizations
            for correlation in sorted(selected.correlations):
                store.lock_correlation(selected.workspace_id,correlation)
            if any(store.for_correlation(selected.workspace_id,correlation) is not None
                    for correlation in selected.correlations): raise _PriorAttempt
            purposes=(DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ)
            intents=(SecretUseIntent.GATEWAY_NODE_HEALTH_READ_TRANSIT_SIGNING_KEY,SecretUseIntent.WORKLOAD_NODE_HEALTH_READ_SIGNING_KEY)
            for index,(purpose,intent) in enumerate(zip(purposes,intents)):
                key=uow.stores.delegation_signing_keys.require_unambiguous_active(selected.workspace_id,purpose)
                expected=selected.inventory[index]
                issuer=(selected.context.transit_issuer,selected.context.workload_issuer)[index]
                if (key.registration_id!=expected["registration_id"] or key.purpose is not purpose
                        or key.workspace_id!=selected.workspace_id or key.issuer!=issuer
                        or key.public_key!=selected.public_keys[index]
                        or key.private_key_reference.reference_id!=expected["private_reference"]): raise ValueError
                command=AuthorizeSecretUse(workspace_id=selected.workspace_id,reference=key.private_key_reference,
                    intent=intent,actor_subject=context.principal.identity.subject_id,
                    actor_scopes=context.granted_scopes,correlation_id=selected.correlations[index],
                    requested_at=datetime.fromtimestamp(_now(clock),timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    operation_id=selected.context.attempt_id,session_id="diagnostic.gateway-health",
                    run_id="diagnostic."+selected.context.attempt_id,
                    activity_id="diagnostic.packet."+selected.packet_digest)
                authorized,provider=authorize_secret_use_in_unit_of_work(uow,command)
                grant=secret_resolution_grant_for(authorized,provider=provider)
                if (grant.reference_registration_id!=expected["reference_registration_id"]
                        or grant.provider_registration_id!=expected["provider_registration_id"]
                        or grant.endpoint_reference.reference_id!=expected["endpoint_reference"]
                        or grant.credential_reference.reference_id!=expected["credential_reference"]): raise ValueError
                projected.append(grant); current_keys.append(key.public_key)
            commit_requested=True
            uow.commit()
        # The actual Postgres commit happens in __exit__, not commit(). A pending
        # cancellation must be observed before the synchronous signer can run.
    except _PriorAttempt:
        return dict(status="prior-attempt-refused",**evidence)
    except Exception:
        return dict(status="commit-uncertain" if commit_requested else "admission-refused",**evidence)
    evidence["authorization_ids"]=[grant.authorization_id for grant in projected]
    await asyncio.sleep(0)
    try:
        _approval(selected,authority,context,clock)  # Reread trusted approval after exit.
        pair=Ed25519HealthCredentialPairSigner(authorized_secret_resolver=authority.resolver,clock=clock).sign(
            selected.context,transit_grant=selected.transit_grant,workload_grant=selected.workload_grant,
            transit_key=HealthSigningKey(current_keys[0],projected[0]),
            workload_key=HealthSigningKey(current_keys[1],projected[1]))
        _approval(selected,authority,context,clock)
    except Exception:
        return dict(status="authorized-not-dispatched",**evidence)
    result=await SignedGatewayHealthClient(clock=clock).dispatch(selected.context,pair,selected.destination,
        transit_grant=selected.transit_grant,workload_grant=selected.workload_grant)
    evidence["status"]=result.code.value
    if result.result is not None: evidence["outcome"]=result.result.outcome.value
    return evidence


def load_authority(path):
    from ._gateway_diagnostic_bootstrap import read_authority
    return read_authority(path)


def main(arguments=None):
    from ._gateway_diagnostic_bootstrap import read_file
    parser=argparse.ArgumentParser(description="Explicit operator gateway self-health diagnostic")
    parser.add_argument("mode",choices=("plan","run"))
    parser.add_argument("--packet",required=True)
    parser.add_argument("--artifacts",default="/run/diagnostic/artifacts")
    parser.add_argument("--bootstrap",default="/run/diagnostic/bootstrap.json")
    args=parser.parse_args(arguments)
    try:
        artifacts={name:read_file(Path(args.artifacts)/(name+".json"),1048576)
            for name in ("control","transit","targets","product")}
        selected=prepare_packet(read_file(Path(args.packet),65536),artifacts)
        if args.mode=="plan":
            result=selected.plan()
        else:
            authority=load_authority(Path(args.bootstrap))
            result=asyncio.run(run_diagnostic(selected,authority,clock=lambda:int(time.time())))
    except (Exception,KeyboardInterrupt):
        result={"status":"diagnostic-unavailable"}
    encoded=json.dumps(result,sort_keys=True,separators=(",",":"))
    if len(encoded.encode())>4096: encoded='{"status":"diagnostic-unavailable"}'
    print(encoded)
    return 0 if result.get("status")=="offline-plan" or (result.get("status")=="received" and result.get("outcome")=="healthy") else 2
