"""Immutable installer bindings; client acquisition follows Operations admission."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat

from control_plane_kit_core.identity import PrincipalIdentity, PrincipalKind
from control_plane_kit_core.secrets import SecretProviderEndpointReference, SecretReference

from control_plane_kit_interpreters.secret_provider import (
    ControlPlaneKitSecretsPolicyClient, SecretProviderClientConfiguration,
)
from control_plane_kit_operations.provider_policy_commands import (
    ProviderPolicyAdministrationDenied, ProviderPolicyAdministrationPolicy,
    ProviderPolicyAdmission, ProviderPolicyBinding,
)


@dataclass(frozen=True, repr=False)
class ProviderPolicyClientBinding:
    binding: ProviderPolicyBinding
    configuration: SecretProviderClientConfiguration

    def __post_init__(self):
        if (type(self.binding) is not ProviderPolicyBinding
                or type(self.configuration) is not SecretProviderClientConfiguration):
            raise ValueError("provider-policy client binding is invalid")
        self.binding.__post_init__()
        self.configuration.__post_init__()


@dataclass(frozen=True, repr=False)
class ProviderPolicyAuthorityConfiguration:
    administration_policy: ProviderPolicyAdministrationPolicy
    bindings: tuple[ProviderPolicyClientBinding, ...]

    def __post_init__(self):
        if (type(self.administration_policy) is not ProviderPolicyAdministrationPolicy
                or type(self.bindings) is not tuple or len(self.bindings) > 1024
                or any(type(item) is not ProviderPolicyClientBinding for item in self.bindings)):
            raise ValueError("provider-policy authority configuration is invalid")
        self.administration_policy.__post_init__()
        for item in self.bindings:
            item.__post_init__()
        if len({item.binding.binding_id for item in self.bindings}) != len(self.bindings):
            raise ValueError("provider-policy client bindings are ambiguous")

    def port(self, binding: ProviderPolicyBinding):
        """Called only by the admitted Operations owner; never discover a fallback."""
        if type(binding) is ProviderPolicyBinding:
            for selected in self.bindings:
                if selected.binding == binding:
                    return ControlPlaneKitSecretsPolicyClient(selected.configuration,
                        binding.logical_provider_id, binding.provider_id)
        raise ProviderPolicyAdministrationDenied("provider-policy binding is unavailable")


_INVALID = "provider-policy authority process configuration is invalid"
_MAX_BYTES = 1_048_576
_INPUT_ERRORS = (ValueError, TypeError, AttributeError, KeyError, OverflowError, RecursionError)


def _object(value, keys):
    if type(value) is not dict or value.keys() != keys:
        raise ValueError
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _constant(value):
    raise ValueError


def decode_provider_policy_authority_configuration(raw: bytes) -> ProviderPolicyAuthorityConfiguration:
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES:
            raise ValueError
        value = _object(json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=_constant), {"schema", "installation_id", "admissions", "bindings"})
        if value["schema"] != "cpk-server.provider-policy-authority.v1":
            raise ValueError
        if any(type(value[key]) is not list or not 1 <= len(value[key]) <= 1024
                for key in ("admissions", "bindings")):
            raise ValueError
        bindings = []
        for item in value["bindings"]:
            _object(item, {"binding_id", "logical_provider_id", "provider_id", "endpoint_reference",
                "base_url", "credential_reference", "credential_file"})
            binding = ProviderPolicyBinding(item["binding_id"], item["logical_provider_id"], item["provider_id"])
            bindings.append(ProviderPolicyClientBinding(binding, SecretProviderClientConfiguration(
                SecretProviderEndpointReference(item["endpoint_reference"]), item["base_url"],
                SecretReference(item["credential_reference"]), Path(item["credential_file"]))))
        by_id = {item.binding.binding_id: item.binding for item in bindings}
        admissions = []
        for item in value["admissions"]:
            _object(item, {"identity", "binding_id"})
            identity = _object(item["identity"], {"issuer", "subject_id", "kind"})
            admissions.append(ProviderPolicyAdmission(PrincipalIdentity(identity["issuer"],
                identity["subject_id"], PrincipalKind(identity["kind"])), by_id[item["binding_id"]]))
        return ProviderPolicyAuthorityConfiguration(
            ProviderPolicyAdministrationPolicy(value["installation_id"], tuple(admissions)), tuple(bindings))
    except _INPUT_ERRORS:
        failure = ValueError(_INVALID)
    raise failure


def read_provider_policy_authority_configuration(path: str) -> ProviderPolicyAuthorityConfiguration:
    """Read installer metadata once; never open a referenced credential here."""
    try:
        if (type(path) is not str or not 1 <= len(path.encode("utf-8")) <= 4096
                or not os.path.isabs(path)
                or any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in path)):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or not 1 <= metadata.st_size <= _MAX_BYTES:
                raise ValueError
            content = bytearray()
            while len(content) <= _MAX_BYTES:
                chunk = os.read(descriptor, min(65_536, _MAX_BYTES + 1 - len(content)))
                if not chunk:
                    break
                content.extend(chunk)
            return decode_provider_policy_authority_configuration(bytes(content))
        finally:
            os.close(descriptor)
    except (*_INPUT_ERRORS, OSError):
        failure = ValueError(_INVALID)
    raise failure
