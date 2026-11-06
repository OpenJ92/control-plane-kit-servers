"""Two-product isolated smoke material; a sample key lives only in this process."""
from __future__ import annotations

from dataclasses import replace
import importlib
import os
from pathlib import Path
import signal
import sys
import time
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import control_plane_kit_core as core
from control_plane_kit_core.http_verification_sample_installation import (
    HttpVerificationSampleReceiverConfiguration, HttpVerificationSampleVerifierConfiguration,
    HttpVerificationSampleCheckBinding,
)
from control_plane_kit_core.http_verification_samples import (
    HttpVerificationSampleRequest, HttpVerificationSampleGrant, HttpVerificationSampleResultCodec,
    http_verification_check_digest, MAX_HTTP_VERIFICATION_SAMPLE_RESULT_BYTES,
)
from control_plane_kit_core.verification import VerificationOutcome


class SampleAuthority:
    """Ephemeral synthetic trust over an independently produced product contract."""
    def __init__(self, control, contract):
        self.control = control
        self.check, = (check for check in contract.verification.checks if check.check_id == "ready")
        self.private = Ed25519PrivateKey.generate()
        public = core.DelegationPublicKey("source-sample", core.DelegationKeyAlgorithm.ED25519,
            self.private.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"))
        self.configuration = HttpVerificationSampleReceiverConfiguration(control.target,
            control.declaration.identity().value, HttpVerificationSampleVerifierConfiguration(
                core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE, "source-sample-witness", (public,)),
            (HttpVerificationSampleCheckBinding("ready", http_verification_check_digest(self.check)),))

    def request(self):
        target = self.control.target
        return HttpVerificationSampleRequest(target=target,
            authority_context=core.NodeControlAuthorityContext("source-sample", "source-sample-projection"),
            declaration_identity=self.control.declaration.identity().value,
            gateway_target=replace(target, receiver_id=uuid4().hex,
                node_id=replace(target.node_id, value="source-sample-witness")),
            route_id="source-route", run_id="source-run", activity_id="source-activity",
            outer_attempt=1, effect_id="source-effect", request_fingerprint="c" * 64,
            check_id="ready", check_digest=http_verification_check_digest(self.check),
            sample_ordinal=1, request_id=uuid4().hex)

    def token(self, request, issued_at):
        verifier = self.configuration.verifier
        grant = HttpVerificationSampleGrant(request=request, purpose=verifier.purpose,
            issuer=verifier.issuer, key_id=verifier.public_keys[0].key_id,
            audience=core.receiver_node_control_audience(self.control.target),
            issued_at=issued_at, not_before=issued_at, expires_at=issued_at + 15, jti=uuid4().hex)
        return jwt.encode(dict(iss=grant.issuer, aud=grant.audience, iat=grant.issued_at,
            nbf=grant.not_before, exp=grant.expires_at, jti=grant.jti,
            workload_http_verification_sample=grant.descriptor()), self.private,
            algorithm="EdDSA", headers={"kid":grant.key_id, "typ":"CPK-WORKLOAD-HTTP-VERIFICATION-SAMPLE+JWT"})


def write_public(path, content):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)
        os.fchmod(stream.fileno(), 0o444)


def require_passed_sample(raw, request, check):
    result = HttpVerificationSampleResultCodec(request, check).decode_canonical_bytes(raw)
    if (result.outcome is not VerificationOutcome.PASSED or result.evidence is None
            or result.evidence.status_code != 200):
        raise ValueError


def witness(product, directory):
    if product == "cpk":
        owner = importlib.import_module("control_plane_kit_servers_cpk_server.control_configuration")
        control = owner.decode_cpk_control_configuration((directory / "control.json").read_bytes())
        contract = owner.cpk_source_runtime_contract(owner.CpkSourceVariant.CPK,
            owner.cpk_control_configuration_artifact(control))
        artifact_factory = owner.cpk_http_sample_configuration_artifact
        url = "http://cpk-source:8080"
    elif product == "secrets":
        owner = importlib.import_module("control_plane_kit_servers_secrets_server.configuration")
        from control_plane_kit_secrets.control import decode_secrets_control_configuration
        control = decode_secrets_control_configuration((directory / "control.json").read_bytes())
        contract = owner.secrets_source_runtime_contract(owner.secrets_control_configuration_artifact(control))
        artifact_factory = owner.secrets_http_sample_configuration_artifact
        url = "http://secrets-provider:8081"
    else:
        raise ValueError
    authority = SampleAuthority(control, contract)
    artifact = artifact_factory(control, authority.configuration)
    write_public(directory / "http-samples.json", artifact.content.encode("utf-8"))
    write_public(directory / "sample.prepared", b"prepared\n")
    # The maintained smoke's existing actual listener readiness phase signals
    # this marker. No grant is minted during image build, startup or that wait.
    deadline = time.monotonic() + 120
    while not (directory / "sample.ready").is_file():
        if time.monotonic() >= deadline:
            raise ValueError
        time.sleep(0.1)
    request = authority.request()
    credential = authority.token(request, int(time.time()))
    with httpx.stream("GET", url + "/__control/verification/http",
            headers={"Authorization":"Bearer " + credential}, timeout=10, trust_env=False) as response:
        if response.status_code != 200:
            raise ValueError
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=4096):
            if len(body) + len(chunk) > MAX_HTTP_VERIFICATION_SAMPLE_RESULT_BYTES:
                raise ValueError
            body.extend(chunk)
    require_passed_sample(bytes(body), request, authority.check)
    write_public(directory / "sample.passed", b"passed\n")


def main():
    def timed_out(signum, frame):
        raise TimeoutError
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(150)
    try:
        if len(sys.argv) != 3:
            raise ValueError
        witness(sys.argv[1], Path(sys.argv[2]))
    except Exception:
        print("source HTTP sample witness failed", file=sys.stderr)
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
