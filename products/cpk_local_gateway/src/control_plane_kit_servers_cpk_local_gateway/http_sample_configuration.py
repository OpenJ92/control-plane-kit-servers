"""One public sample-trust parser for gateway startup and composition adapters."""
from dataclasses import replace
import json
import os
import time

import control_plane_kit_core as core
from control_plane_kit_core.configuration import (
    ConfigurationArtifact, ConfigurationArtifactRequirement, ConfigurationMediaType, ConfigurationFileMode,
)
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from .health_transit_configuration import _decode_json, _object, _INPUT_ERRORS
from .health_relay_startup import _read
from .http_sample_relay import GatewayHttpSampleTrust, GatewayHttpSampleRelay

ARTIFACT_ID = "gateway-http-sample-transit"
CONFIGURATION_PATH = "/etc/cpk/gateway/http-sample-transit.json"
CONFIGURATION_ENVIRONMENT = "CPK_GATEWAY_HTTP_SAMPLE_TRANSIT_CONFIGURATION_FILE"
PROFILE = "cpk-gateway-http-sample-transit-configuration.v1"
MAX_CONFIGURATION_BYTES = 16384
_FIELDS = frozenset({"profile", "gateway_target", "purpose", "issuer", "public_keys"})
_KEY_FIELDS = frozenset({"key_id", "algorithm", "public_key_pem"})
_ERROR = "gateway HTTP sample configuration is invalid"


class GatewayHttpSampleConfigurationError(ValueError):
    """Fixed public-material refusal, without peer/candidate diagnostics."""


def decode_gateway_http_sample_trust(raw):
    try:
        value = _object(_decode_json(raw, MAX_CONFIGURATION_BYTES), _FIELDS)
        if (value["profile"] != PROFILE
                or value["purpose"] != core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT.value
                or type(value["public_keys"]) is not list or not 1 <= len(value["public_keys"]) <= 16):
            raise ValueError
        keys = []
        for key in value["public_keys"]:
            key = _object(key, _KEY_FIELDS)
            if any(type(key[name]) is not str for name in _KEY_FIELDS):
                raise ValueError
            keys.append(core.DelegationPublicKey(key["key_id"], core.DelegationKeyAlgorithm(key["algorithm"]),
                                                key["public_key_pem"]))
        return GatewayHttpSampleTrust(core.NodeControlReceiverTargetCodec().decode(value["gateway_target"]),
                                      value["issuer"], tuple(keys))
    except _INPUT_ERRORS:
        failure = GatewayHttpSampleConfigurationError(_ERROR)
    raise failure


def gateway_http_sample_trust_artifact(trust):
    try:
        if type(trust) is not GatewayHttpSampleTrust:
            raise ValueError
        trust = replace(trust)
        content = json.dumps(dict(profile=PROFILE, gateway_target=trust.gateway_target.descriptor(),
            purpose=core.DelegationKeyPurpose.GATEWAY_HTTP_VERIFICATION_SAMPLE_TRANSIT.value,
            issuer=trust.issuer, public_keys=[dict(key_id=key.key_id, algorithm=key.algorithm.value,
                public_key_pem=key.public_key_pem) for key in trust.public_keys]),
            sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        decode_gateway_http_sample_trust(content.encode())
        return ConfigurationArtifact(ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON,
                                     content, ConfigurationFileMode.READ_ONLY)
    except _INPUT_ERRORS:
        failure = GatewayHttpSampleConfigurationError(_ERROR)
    raise failure


def gateway_http_sample_trust_from_artifact(artifact):
    try:
        if type(artifact) is not ConfigurationArtifact:
            raise ValueError
        checked = ConfigurationArtifact.from_descriptor(artifact.descriptor())
        if (checked.artifact_id != ARTIFACT_ID or checked.target_path != CONFIGURATION_PATH
                or checked.media_type is not ConfigurationMediaType.JSON
                or checked.file_mode is not ConfigurationFileMode.READ_ONLY):
            raise ValueError
        return decode_gateway_http_sample_trust(checked.content.encode("utf-8"))
    except _INPUT_ERRORS:
        failure = GatewayHttpSampleConfigurationError(_ERROR)
    raise failure


def gateway_http_sample_declared_runtime_contract():
    from .health_relay_configuration import gateway_health_declared_runtime_contract
    contract = gateway_health_declared_runtime_contract()
    return replace(contract, configuration_requirements=contract.configuration_requirements + (
        ConfigurationArtifactRequirement(ARTIFACT_ID, CONFIGURATION_PATH, ConfigurationMediaType.JSON,
                                         ConfigurationFileMode.READ_ONLY),),
        public_environment=contract.public_environment + (
            PublicStaticEnvironmentBinding(CONFIGURATION_ENVIRONMENT, CONFIGURATION_PATH),))


def gateway_http_sample_source_runtime_contract(health_trust, routes, control, sample_trust):
    from .health_relay_configuration import gateway_health_source_runtime_contract
    from .control_configuration import gateway_control_configuration_from_artifact
    try:
        contract = gateway_health_source_runtime_contract(health_trust, routes, control)
        own = gateway_control_configuration_from_artifact(control)
        trust = gateway_http_sample_trust_from_artifact(sample_trust)
        if trust.gateway_target != own.target:
            raise ValueError
        return replace(contract, configuration_artifacts=contract.configuration_artifacts + (sample_trust,),
            public_environment=contract.public_environment + (
                PublicStaticEnvironmentBinding(CONFIGURATION_ENVIRONMENT, CONFIGURATION_PATH),))
    except _INPUT_ERRORS:
        failure = GatewayHttpSampleConfigurationError(_ERROR)
    raise failure


def load_http_sample_relay(health_relay, control):
    """Explicit fixed file selection; absence leaves the new surface disabled."""
    if CONFIGURATION_ENVIRONMENT not in os.environ:
        return None
    try:
        if os.environ[CONFIGURATION_ENVIRONMENT] != CONFIGURATION_PATH:
            raise ValueError
        trust = decode_gateway_http_sample_trust(_read(CONFIGURATION_PATH, MAX_CONFIGURATION_BYTES))
        if trust.gateway_target != control.target:
            raise ValueError
        return GatewayHttpSampleRelay(health_relay.configuration, trust, clock=time.time)
    except (OSError, *_INPUT_ERRORS):
        failure = GatewayHttpSampleConfigurationError(_ERROR)
    raise failure
