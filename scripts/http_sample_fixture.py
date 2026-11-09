"""Two-product isolated smoke material; a sample key lives only in this process."""
from __future__ import annotations

from dataclasses import replace
import importlib
import json
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
    def __init__(self, control, contract, *, all_checks=False):
        self.control = control
        self.check, = (check for check in contract.verification.checks if check.check_id == "ready")
        self.checks = tuple(contract.verification.checks) if all_checks else (self.check,)
        self.private = Ed25519PrivateKey.generate()
        public = core.DelegationPublicKey("source-sample", core.DelegationKeyAlgorithm.ED25519,
            self.private.public_key().public_bytes(serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"))
        self.configuration = HttpVerificationSampleReceiverConfiguration(control.target,
            control.declaration.identity().value, HttpVerificationSampleVerifierConfiguration(
                core.DelegationKeyPurpose.WORKLOAD_HTTP_VERIFICATION_SAMPLE, "source-sample-witness", (public,)),
            tuple(HttpVerificationSampleCheckBinding(check.check_id, http_verification_check_digest(check))
                for check in self.checks))

    def request(self, check=None):
        check = self.check if check is None else check
        target = self.control.target
        return HttpVerificationSampleRequest(target=target,
            authority_context=core.NodeControlAuthorityContext("source-sample", "source-sample-projection"),
            declaration_identity=self.control.declaration.identity().value,
            gateway_target=replace(target, receiver_id=uuid4().hex,
                node_id=replace(target.node_id, value="source-sample-witness")),
            route_id="source-route", run_id="source-run", activity_id="source-activity",
            outer_attempt=1, effect_id="source-effect", request_fingerprint="c" * 64,
            check_id=check.check_id, check_digest=http_verification_check_digest(check),
            sample_ordinal=1, request_id=uuid4().hex)

    def token(self, request, issued_at, *, issuer=None):
        verifier = self.configuration.verifier
        grant = HttpVerificationSampleGrant(request=request, purpose=verifier.purpose,
            issuer=verifier.issuer if issuer is None else issuer, key_id=verifier.public_keys[0].key_id,
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


def witness(product, directory, *, all_checks=False):
    if product == "cpk":
        owner = importlib.import_module("control_plane_kit_servers_cpk_server.control_configuration")
        control = owner.decode_cpk_control_configuration((directory / "control.json").read_bytes())
        variant = owner.CpkSourceVariant.DOCKER_CLOUDFLARE if all_checks else owner.CpkSourceVariant.CPK
        contract = owner.cpk_source_runtime_contract(variant,
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
    authority = SampleAuthority(control, contract, all_checks=all_checks)
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
    results = []
    for check in authority.checks:
        request = authority.request(check)
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
        require_passed_sample(bytes(body), request, check)
        if all_checks:
            # Both tokens are cryptographically valid under the installed key;
            # the wrong issuer must nevertheless have no authority.
            wrong = authority.token(request, int(time.time()), issuer="foreign-source-witness")
            for headers in ({}, {"Authorization": "Bearer " + wrong}):
                with httpx.stream("GET", url + "/__control/verification/http", headers=headers,
                        timeout=3, trust_env=False) as response:
                    if response.status_code != 401:
                        raise ValueError
                    response.close()
            results.append({"check_id": check.check_id, "passed": True,
                "absent_authority_status": 401, "wrong_issuer_status": 401})
    if all_checks:
        write_public(directory / "sample.passed", json.dumps({
            "checks": results, "target": control.target.descriptor(),
            "declaration_identity": control.declaration.identity().value,
            "fixture_delta": "fresh-synthetic-receiver-and-signers-no-approved-child-run"}, sort_keys=True).encode())
    else:
        write_public(directory / "sample.passed", b"passed\n")


def main():
    def timed_out(signum, frame):
        raise TimeoutError
    signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(180 if len(sys.argv) == 4 else 150)
    try:
        if len(sys.argv) not in (3, 4) or (len(sys.argv) == 4 and sys.argv[3] != "all-checks"):
            raise ValueError
        witness(sys.argv[1], Path(sys.argv[2]), all_checks=len(sys.argv) == 4)
    except Exception:
        print("source HTTP sample witness failed", file=sys.stderr)
        return 1
    finally:
        signal.alarm(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
