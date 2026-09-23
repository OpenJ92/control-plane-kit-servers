"""Offline source-artifact selection for an explicitly approved diagnostic."""
from dataclasses import dataclass, replace
from hashlib import sha256
import json
import re
from types import MappingProxyType

import rfc8785
import control_plane_kit_core as core
from control_plane_kit_core.products import ProductDescriptorCodec
from control_plane_kit_core.public_ingress import NamedPublicIngressCodec
from control_plane_kit_interpreters.probes.health_signing import HealthSigningContext
from control_plane_kit_interpreters.probes.health_transport import SelectedManagementGateway
from control_plane_kit_servers_cpk_local_gateway import control_configuration as control
from control_plane_kit_servers_cpk_local_gateway import health_transit_configuration as transit
from control_plane_kit_servers_cpk_local_gateway import health_relay_configuration as relay


class DiagnosticInputError(ValueError):
    def __init__(self): super().__init__("diagnostic input unavailable")


def closed(value, fields):
    if type(value) is not dict or set(value) != set(fields): raise ValueError
    return value


def unique(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError
        result[key]=value
    return result


def bounded_json(raw, maximum=65536):
    if type(raw) is not bytes or not 1 <= len(raw) <= maximum: raise ValueError
    return json.loads(raw.decode("utf-8"),object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))


def reference(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}",value): raise ValueError
    return value


@dataclass(frozen=True,repr=False)
class PreparedDiagnostic:
    packet_digest: str
    context: HealthSigningContext
    destination: SelectedManagementGateway
    transit_grant: object
    workload_grant: object
    public_keys: tuple
    inventory: tuple
    artifact_digests: object
    source_commit: str
    image_digest: str
    resource_plan: str

    @property
    def workspace_id(self): return self.context.request.target.workspace_id.value

    @property
    def correlations(self):
        return tuple("diagnostic-health:"+sha256(rfc8785.dumps(
            [self.workspace_id,self.context.attempt_id,family])).hexdigest()
            for family in ("transit","workload"))

    def plan(self):
        return dict(status="offline-plan",packet_digest=self.packet_digest,
            request_digest=self.context.request.canonical_digest().value,
            attempt_id=self.context.attempt_id,authorization_writes=2,
            artifact_digests=dict(self.artifact_digests),source_commit=self.source_commit,
            image_digest=self.image_digest,resource_plan=self.resource_plan,
            missing_prerequisites=["authenticated-approval","existing-custody-inventory","live-resource-plan"])


def prepare_packet(raw, artifacts):
    try:
        packet=closed(bounded_json(raw),{"profile","attempt_id","request","ingress","target_id",
            "transit_socket","source_commit","image_digest","resource_plan","artifacts",
            "transit_grant","workload_grant","keys"})
        if packet["profile"] != "gateway-self-health-diagnostic.v1": raise ValueError
        canonical=rfc8785.dumps(packet)
        if canonical != raw: raise ValueError
        for name in ("attempt_id","target_id","transit_socket","resource_plan"): reference(packet[name])
        if not re.fullmatch(r"[0-9a-f]{40}",packet["source_commit"]): raise ValueError
        if not re.fullmatch(r"sha256:[0-9a-f]{64}",packet["image_digest"]): raise ValueError
        names={"control","transit","targets","product"}
        closed(packet["artifacts"],names)
        if type(artifacts) is not dict or set(artifacts) != names: raise ValueError
        for name in names:
            if type(artifacts[name]) is not bytes or not 1 <= len(artifacts[name]) <= 1048576: raise ValueError
            if sha256(artifacts[name]).hexdigest() != packet["artifacts"][name]: raise ValueError
        document=ProductDescriptorCodec().decode_document(artifacts["product"])
        contract=document.product.runtime_contract
        slots={"control":("gateway-control",control.CONTROL_PATH),
            "transit":(transit.ARTIFACT_ID,transit.CONFIGURATION_PATH),
            "targets":(relay.ARTIFACT_ID,relay.CONFIGURATION_PATH)}
        selected={}
        for name,(identity,path) in slots.items():
            matches=tuple(item for item in contract.configuration_artifacts if item.artifact_id==identity)
            if len(matches)!=1: raise ValueError
            item,=matches
            if (item.target_path!=path or item.media_type.value!="application/json"
                    or item.file_mode.value!="0444"): raise ValueError
            selected[name]=replace(item,content=artifacts[name].decode("utf-8"))
        configured=control.decode_gateway_control_configuration(artifacts["control"])
        trust=transit.decode_gateway_health_transit_configuration(artifacts["transit"])
        targets=relay.decode_gateway_health_relay_configuration(artifacts["targets"])
        relay.require_matching_receiver(trust,targets)
        control.require_matching_gateway_control(configured,targets)
        actual=relay.gateway_health_source_runtime_contract(selected["transit"],selected["targets"],selected["control"])
        if (actual.gateway_transit!=contract.gateway_transit or actual.control_surfaces!=contract.control_surfaces
                or actual.sockets!=contract.sockets or actual.provider_ports!=contract.provider_ports): raise ValueError
        bindings=tuple(item for item in targets.targets if item.target==configured.target
            and item.runtime_id==configured.runtime_id and item.declaration==configured.declaration)
        if len(bindings)!=1: raise ValueError
        binding,=bindings
        request=core.NodeHealthReadRequestCodec().decode(packet["request"])
        ingress=NamedPublicIngressCodec().decode(packet["ingress"])
        if (request.target!=configured.target or request.runtime_id!=configured.runtime_id
                or request.kind is not core.NodeHealthReadKind.READINESS
                or request.declaration_identity!=configured.declaration.identity()
                or binding.target_id!=packet["target_id"]
                or packet["transit_socket"]!=contract.gateway_transit.provider_socket_name
                or ingress.target.node_id!=configured.target.node_id.value
                or ingress.target.provider_socket!=packet["transit_socket"]): raise ValueError
        context=HealthSigningContext(request,packet["attempt_id"],configured.target.node_id,
            configured.declaration,trust.issuer,configured.health_issuer)
        grants=(core.DelegatedGatewayNodeHealthReadTransitGrantCodec().decode(packet["transit_grant"]),
                core.DelegatedWorkloadNodeHealthReadGrantCodec().decode(packet["workload_grant"]))
        if (grants[0].issued_at,grants[0].not_before,grants[0].expires_at)!=(
                grants[1].issued_at,grants[1].not_before,grants[1].expires_at): raise ValueError
        if type(packet["keys"]) is not list or len(packet["keys"])!=2: raise ValueError
        publics=[]
        inventory=[]
        for item,grant,available in zip(packet["keys"],grants,(trust.public_keys,configured.health_keys.public_keys)):
            closed(item,{"registration_id","key_id","fingerprint","private_reference","reference_registration_id",
                "provider_registration_id","endpoint_reference","credential_reference"})
            for value in item.values(): reference(value)
            keys=tuple(key for key in available if key.key_id==item["key_id"] and key.fingerprint_sha256==item["fingerprint"])
            if len(keys)!=1 or grant.key_id!=item["key_id"]: raise ValueError
            publics.append(keys[0]); inventory.append(MappingProxyType(dict(item)))
        if publics[0].fingerprint_sha256==publics[1].fingerprint_sha256: raise ValueError
        from control_plane_kit_core.node_health_reads import verify_workload_node_health_read_grant
        from control_plane_kit_core.node_health_transit import verify_gateway_node_health_read_transit_grant
        expected=dict(expected_target=request.target,expected_runtime_id=request.runtime_id,
            expected_declaration=configured.declaration,expected_kind=request.kind,now=grants[0].not_before)
        if not verify_gateway_node_health_read_transit_grant(grants[0],request,
                expected_issuer=context.transit_issuer,expected_key_id=publics[0].key_id,
                expected_attempt_id=context.attempt_id,expected_gateway_node_id=context.gateway_node_id,**expected).is_accepted: raise ValueError
        if not verify_workload_node_health_read_grant(grants[1],request,
                expected_issuer=context.workload_issuer,expected_key_id=publics[1].key_id,
                expected_audience=core.workload_node_control_audience(request.target),**expected).is_accepted: raise ValueError
        return PreparedDiagnostic(sha256(canonical).hexdigest(),context,
            SelectedManagementGateway(ingress,context.gateway_node_id,packet["transit_socket"],request.runtime_id,binding.target_id),
            *grants,tuple(publics),tuple(inventory),MappingProxyType(dict(packet["artifacts"])),
            packet["source_commit"],packet["image_digest"],packet["resource_plan"])
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        failure=DiagnosticInputError()
    raise failure
