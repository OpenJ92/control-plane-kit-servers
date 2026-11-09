"""One owned fixture lifetime for packaged gateway HTTP sample qualification.

Public configuration only is written. Private fixture keys remain in this
controller; callers own image identity, container launch and exact cleanup.
Neither a helper result nor its synthetic grants establish an approved run.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import json
from pathlib import Path
import signal
import sys
import time
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import httpx
import jwt
import rfc8785
import control_plane_kit_core as core
from control_plane_kit_core.http_verification_sample_installation import (
    HttpVerificationSampleReceiverConfiguration, HttpVerificationSampleVerifierConfiguration,
    HttpVerificationSampleCheckBinding,
)
from control_plane_kit_core.http_verification_samples import (
    HttpVerificationSampleRequest, HttpVerificationSampleGrant, http_verification_check_digest,
    MAX_HTTP_VERIFICATION_SAMPLE_RESULT_BYTES,
)
from control_plane_kit_core.wrapper_configuration import NodeControlVerificationConfiguration
from control_plane_kit_servers_cpk_server import control_configuration as cpk
from control_plane_kit_servers_secrets_server import configuration as secrets
from control_plane_kit_secrets.control import secrets_control_declaration
from control_plane_kit_servers_cpk_local_gateway import control_configuration as gateway
from control_plane_kit_servers_cpk_local_gateway.health_transit_configuration import (
    GatewayHealthTransitConfiguration, gateway_health_transit_configuration_artifact,
)
from control_plane_kit_servers_cpk_local_gateway.health_relay_configuration import gateway_health_relay_configuration_artifact
from control_plane_kit_servers_cpk_local_gateway.http_sample_configuration import (
    gateway_http_sample_source_runtime_contract, gateway_http_sample_trust_artifact,
)
from control_plane_kit_servers_cpk_local_gateway.http_sample_relay import GatewayHttpSampleTrust
from scripts.http_sample_fixture import require_passed_sample, write_public


def _require(value):
    if value is not True:
        raise ValueError("gateway sample fixture failed")


def _key(name):
    private = Ed25519PrivateKey.generate()
    public = core.DelegationPublicKey(name, core.DelegationKeyAlgorithm.ED25519,
        private.public_key().public_bytes(serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"))
    return private, public


def _target(node, socket):
    roles = core.NodeControlGraphReferenceRole
    return core.NodeControlReceiverTarget(*(core.NodeControlGraphReference(role, value) for role, value in (
        (roles.WORKSPACE, "root-workspace"), (roles.RUNTIME, "root-a-docker"),
        (roles.NODE, node), (roles.PROVIDER_SOCKET, socket))), uuid4().hex)


@dataclass(frozen=True, repr=False)
class ReceiverMaterial:
    control: object
    contract: object
    artifacts: tuple
    origin: str


class GatewaySampleFixture:
    """Test-owned authority, never authorization from Operations or a provider."""
    def __init__(self, *, clock=time.time):
        self.clock = clock
        self._surface_private, surface = _key("fixture-surface")
        self._health_private, health = _key("fixture-health")
        self._health_transit_private, health_transit = _key("fixture-health-transit")
        self.health_public, self.health_transit_public = health, health_transit
        self._workload_private, self.workload_public = _key("fixture-http-workload")
        self._transit_private, self.transit_public = _key("fixture-http-transit")
        self.workload_issuer, self.transit_issuer = "source-163-workload", "source-163-transit"
        self.gateway_target = _target("root-a-gateway", "control")
        families = (
            NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_CONTROL_SURFACE_READ,
                "source-163-surface", (surface,)),
            NodeControlVerificationConfiguration(core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ,
                "source-163-health", (health,)))
        self.gateway_control = core.ReceiverNodeControlConfiguration(self.gateway_target,
            gateway.gateway_control_declaration(), families)
        controls = {
            "cpk": core.ReceiverNodeControlConfiguration(_target("root-a-cpk", "http-api"), cpk.cpk_control_declaration(), families),
            "secrets": core.ReceiverNodeControlConfiguration(_target("root-a-secrets", "control"), secrets_control_declaration(), families),
        }
        verifier = HttpVerificationSampleVerifierConfiguration(
            core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE,
            self.workload_issuer, (self.workload_public,))
        self.receivers = {}
        for role, control in controls.items():
            if role == "cpk":
                artifact = cpk.cpk_control_configuration_artifact(control)
                contract = cpk.cpk_source_runtime_contract(cpk.CpkSourceVariant.DOCKER_CLOUDFLARE, artifact)
                factory, origin = cpk.cpk_http_sample_configuration_artifact, "http://cpk-source:8080"
            else:
                artifact = secrets.secrets_control_configuration_artifact(control)
                contract = secrets.secrets_source_runtime_contract(artifact)
                factory, origin = secrets.secrets_http_sample_configuration_artifact, "http://secrets-provider:8081"
            _require(tuple(check.check_id for check in contract.verification.checks) == ("live", "ready"))
            companion = factory(control, HttpVerificationSampleReceiverConfiguration(control.target,
                control.declaration.identity().value, verifier, tuple(HttpVerificationSampleCheckBinding(
                    check.check_id, http_verification_check_digest(check)) for check in contract.verification.checks)))
            self.receivers[role] = ReceiverMaterial(control, contract, (artifact, companion), origin)
        self.routes = core.ReceiverManagementRoutes(self.gateway_target, tuple(
            core.ReceiverManagementRouteBinding(role, value.control.target, value.control.declaration, value.origin)
            for role, value in self.receivers.items()))
        self.transit_trust = GatewayHttpSampleTrust(self.gateway_target, self.transit_issuer, (self.transit_public,))
        self.gateway_artifacts = (
            gateway_health_transit_configuration_artifact(GatewayHealthTransitConfiguration(self.gateway_target,
                "source-163-health-transit", core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT, (health_transit,))),
            gateway_health_relay_configuration_artifact(self.routes),
            gateway.gateway_control_configuration_artifact(self.gateway_control),
            gateway_http_sample_trust_artifact(self.transit_trust))
        self.gateway_contract = gateway_http_sample_source_runtime_contract(*self.gateway_artifacts)

    def write(self, directory):
        """Fresh public-only directory; caller owns its lifecycle and mounts."""
        directory = Path(directory)
        directory.mkdir(mode=0o700)
        artifacts = {role: value.artifacts for role, value in self.receivers.items()}
        artifacts["gateway"] = self.gateway_artifacts
        for role, values in artifacts.items():
            (directory / role).mkdir(mode=0o700)
            for artifact in values:
                write_public(directory / role / Path(artifact.target_path).name, artifact.content.encode("utf-8"))
        write_public(directory / "prepared", b"prepared\n")

    def request(self, role, check):
        receiver = self.receivers[role]
        _require(check in receiver.contract.verification.checks)
        return HttpVerificationSampleRequest(target=receiver.control.target,
            authority_context=core.NodeControlAuthorityContext("source-163-gateway", "source-163-projection"),
            declaration_identity=receiver.control.declaration.identity().value, gateway_target=self.gateway_target,
            route_id=role, run_id="source-163-run", activity_id="source-163-activity", outer_attempt=1,
            effect_id="source-163-effect", request_fingerprint="c" * 64, check_id=check.check_id,
            check_digest=http_verification_check_digest(check), sample_ordinal=1, request_id=uuid4().hex)

    def token(self, request, *, transit=False, foreign_issuer=False, expired=False, purpose=None):
        public = self.transit_public if transit else self.workload_public
        purpose = purpose or (core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT if transit
            else core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE)
        issuer = self.transit_issuer if transit else self.workload_issuer
        if foreign_issuer:
            issuer = "foreign-source-witness"
        now = int(self.clock())
        issued, expires = (now - 3, now - 1) if expired else (now, now + 15)
        grant = HttpVerificationSampleGrant(request=request, purpose=purpose, issuer=issuer, key_id=public.key_id,
            audience=self.transit_trust.audience if transit else core.receiver_node_control_audience(request.target),
            issued_at=issued, not_before=issued, expires_at=expires, jti=uuid4().hex)
        claim, typ = (("gateway_http_verification_sample_transit", "CPK-GATEWAY-HTTP-VERIFICATION-SAMPLE-TRANSIT+JWT")
            if transit else ("workload_http_verification_sample", "CPK-WORKLOAD-HTTP-VERIFICATION-SAMPLE+JWT"))
        return jwt.encode(dict(iss=issuer, aud=grant.audience, iat=issued, nbf=issued, exp=expires,
            jti=grant.jti, **{claim:grant.descriptor()}), self._transit_private if transit else self._workload_private,
            algorithm="EdDSA", headers={"typ":typ, "kid":public.key_id})

    def health_pair(self, role):
        """Separate generic V2 LIVENESS family, never a named HTTP ready check."""
        receiver = self.receivers[role]
        request = core.ReceiverHealthReadRequest(receiver.control.target,
            core.NodeControlAuthorityContext("source-163-gateway", "source-163-projection"),
            core.NodeHealthReadKind.LIVENESS, receiver.control.declaration.identity(), uuid4().hex)
        now, attempt = int(self.clock()), uuid4().hex
        common = dict(canonicalization=core.NodeControlCanonicalization.JCS_RFC8785_V1,
            target=request.target, authority_context=request.authority_context, kind=request.kind,
            declaration_identity=request.declaration_identity, request_id=request.request_id,
            request_digest=request.canonical_digest(), issued_at=now, not_before=now, expires_at=now+15)
        workload = core.DelegatedWorkloadReceiverHealthReadGrant(**common,
            profile=core.DelegatedWorkloadReceiverHealthReadGrantProfile.V2,
            purpose=core.DelegationKeyPurpose.WORKLOAD_NODE_HEALTH_READ, issuer="source-163-health",
            key_id=self.health_public.key_id, audience=core.receiver_node_control_audience(request.target), jti=uuid4().hex)
        transit = core.DelegatedGatewayReceiverHealthReadTransitGrant(**common,
            profile=core.DelegatedGatewayReceiverHealthReadTransitGrantProfile.V2,
            purpose=core.DelegationKeyPurpose.GATEWAY_NODE_HEALTH_READ_TRANSIT,
            issuer="source-163-health-transit", key_id=self.health_transit_public.key_id,
            gateway_target=self.gateway_target, attempt_id=attempt, jti=uuid4().hex)
        def encode(grant, private, typ, claim):
            return jwt.encode(dict(iss=grant.issuer, aud=grant.audience, iat=now, nbf=now,
                exp=now+15, jti=grant.jti, **{claim:grant.descriptor()}), private, algorithm="EdDSA",
                headers={"typ":typ, "kid":grant.key_id})
        return request, attempt, encode(workload, self._health_private,
            "CPK-WORKLOAD-NODE-HEALTH-READ+JWT", "workload_node_health_read"), encode(transit,
            self._health_transit_private, "CPK-GATEWAY-NODE-HEALTH-READ-TRANSIT+JWT", "gateway_node_health_read_transit")

    async def exercise(self, *, transport=None):
        """Real network by default; unit transports prove no packaged behavior."""
        rows, health_rows = [], []
        async with httpx.AsyncClient(transport=transport, timeout=10, trust_env=False,
                follow_redirects=False) as client:
            async def send_frame(path, envelope, credential):
                headers = {"Content-Type":"application/json", "Accept-Encoding":"identity"}
                if credential is not None:
                    headers["Authorization"] = "Bearer " + credential
                async with client.stream("POST", "http://gateway-source:8000" + path,
                        headers=headers, content=rfc8785.dumps(envelope)) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=4096):
                        _require(len(body) + len(chunk) <= MAX_HTTP_VERIFICATION_SAMPLE_RESULT_BYTES)
                        body.extend(chunk)
                    return response.status_code, bytes(body)

            async def post(request, workload, transit, *, selector=None):
                return await send_frame("/cpk/verification/http", dict(
                    profile="cpk-gateway-http-verification-sample-request.v1",
                    target_id=request.route_id if selector is None else selector,
                    request=request.descriptor(), workload_credential=workload), transit)

            for role, receiver in self.receivers.items():
                for check in receiver.contract.verification.checks:
                    request = self.request(role, check)
                    workload, transit = self.token(request), self.token(request, transit=True)
                    status, raw = await post(request, workload, transit)
                    _require(status == 200)
                    require_passed_sample(raw, request, check)
                    other_role = next(value for value in self.receivers if value != role)
                    crossed_target = replace(request, target=self.receivers[other_role].control.target)
                    crossed_check = replace(request, check_digest="e" * 64)
                    negatives = (
                        ("missing_transit", request, {}, None, None, 401),
                        ("foreign_transit_issuer", request, {}, {"foreign_issuer":True}, None, 401),
                        ("wrong_transit_purpose", request, {}, {"purpose":core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE}, None, 401),
                        ("unknown_selector", request, {}, {}, "not-installed", 403),
                        ("crossed_selector", request, {}, {}, other_role, 403),
                        ("crossed_workload_target", crossed_target, {}, {}, None, 403),
                        ("crossed_workload_check", crossed_check, {}, {}, None, 403),
                        ("expired_transit", request, {}, {"expired":True}, None, 504),
                        ("expired_workload", request, {"expired":True}, {}, None, 504),
                        ("foreign_workload_issuer", request, {"foreign_issuer":True}, {}, None, 502),
                    )
                    refusals = {}
                    for name, workload_request, workload_options, transit_options, selector, expected in negatives:
                        # Fresh control tokens per exchange: a slow earlier refusal
                        # cannot turn a later selector/purpose test into expiry.
                        candidate_workload = self.token(workload_request, **workload_options)
                        candidate_transit = (None if transit_options is None else
                            self.token(request, transit=True, **transit_options))
                        status, raw = await post(request, candidate_workload, candidate_transit, selector=selector)
                        _require(status == expected and set(json.loads(raw)) == {"code"})
                        refusals[name] = dict(status=status, forwarding="not-observed", child_refusal="not-observed")
                    rows.append(dict(role=role, check_id=check.check_id, request_id=request.request_id,
                        check_digest=request.check_digest, target=request.target.descriptor(), passed=True,
                        refusals=refusals))
            for role, receiver in self.receivers.items():
                request, attempt, workload, transit = self.health_pair(role)
                frame = dict(profile="cpk-gateway-health-relay-request.v2", target_id=role,
                    attempt_id=attempt, request=request.descriptor(), workload_credential=workload)
                status, raw = await send_frame("/cpk/health/liveness", frame, transit)
                _require(status == 200)
                result = core.ReceiverHealthReadResultCodec(request, receiver.control.declaration).decode(json.loads(raw))
                _require(result.outcome is core.NodeHealthReadOutcome.HEALTHY)
                # A valid HTTP-transit credential is not generic V2 authority.
                request, attempt, workload, _ = self.health_pair(role)
                frame = dict(profile="cpk-gateway-health-relay-request.v2", target_id=role,
                    attempt_id=attempt, request=request.descriptor(), workload_credential=workload)
                sample = self.request(role, receiver.contract.verification.checks[0])
                status, _ = await send_frame("/cpk/health/liveness", frame, self.token(sample, transit=True))
                _require(status == 401)
                # Nor is a valid generic V2 transit a named HTTP sample grant.
                _, _, _, transit = self.health_pair(role)
                status, _ = await post(sample, self.token(sample), transit)
                _require(status == 401)
                health_rows.append(dict(role=role, kind="liveness", passed=True,
                    http_transit_refused=401, v2_transit_refused_for_http=401))
        return dict(evidence="gateway-relay-exchange-only", samples=rows, health_relays=health_rows,
            gateway_target=self.gateway_target.descriptor(),
            workload_public_fingerprint=self.workload_public.fingerprint_sha256,
            transit_public_fingerprint=self.transit_public.fingerprint_sha256,
            forwarding_wire_observation="not-instrumented-by-this-controller",
            child_health_probe_count="not-observed", approved_run=False,
            fixture_delta="fresh-synthetic-authorities-no-operations-history")


def main():
    def timeout(*_):
        raise TimeoutError
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(240)
    try:
        _require(len(sys.argv) == 2)
        fixture = GatewaySampleFixture()
        directory = Path(sys.argv[1])
        fixture.write(directory)
        deadline = time.monotonic() + 120
        while not (directory / "ready").is_file():
            _require(time.monotonic() < deadline)
            time.sleep(0.1)
        result = asyncio.run(fixture.exercise())
        write_public(directory / "samples.json", rfc8785.dumps(result))
        return 0
    except Exception:
        print("gateway sample fixture failed", file=sys.stderr)
        return 1
    finally:
        signal.alarm(0)


if __name__ == "__main__":
    raise SystemExit(main())
