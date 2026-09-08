"""Pure Docker installation composition shared by bootstrap and public clients.

This product-owned bootstrap composition declares existing process inputs. It
does not resolve secrets, admit authority, contact providers, or execute a plan.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
from urllib.parse import urlsplit

from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime, SocketConnection
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.lifecycle import ResourcePersistence
from control_plane_kit_core.products import (
    ContainerServerProduct,
    ProductDescriptorCodec,
    ProductDescriptorDocument,
    ProductIdentity,
    ProductInstanceConfiguration,
    ProductRuntimeContract,
    ProductRuntimeContractCodec,
    instantiate_product,
)
from control_plane_kit_core.public_ingress import NamedPublicIngress, PublicIngressTarget
from control_plane_kit_core.runtime_authority import (
    RuntimeAuthorityAccessDelivery,
    RuntimeAuthorityAccessDeliveryKind,
    RuntimeAuthorityReference,
)
from control_plane_kit_core.secrets import (
    SecretEnvironmentDelivery,
    SecretFileDelivery,
    SecretFilePathBinding,
    SecretProviderEndpointReference,
    SecretReference,
    SecretUseIntent,
)
from control_plane_kit_core.verification import PostgresQueryCheck


_INSTALLATION_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_WORKSPACE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
_STORES = ("workplace-store", "activity-history-store", "observer-state-store",
           "graph-topology-store")
_PROVIDER_CLIENT_FILE = "/run/secrets/cpk-installation/provider-client"


@dataclass(frozen=True)
class ExternalInstallationIngress:
    """An externally supplied endpoint, without graph ownership of its ingress."""

    endpoint: str

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, str) or len(self.endpoint) > 2048:
            raise ValueError("external installation endpoint must be bounded HTTPS")
        parsed = urlsplit(self.endpoint)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ("", "/") or any(c.isspace() for c in self.endpoint)):
            raise ValueError("external installation endpoint must be credential-free HTTPS")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("external installation endpoint port is invalid")


@dataclass(frozen=True, kw_only=True)
class DockerCpkInstallation:
    """Immutable desired values; all credential inputs are unresolved references.

    ``runtime_authority`` selects the enclosing deployment runtime. Separately,
    ``runtime_access`` must be admitted for ``cpk_node_id`` by the driver/client;
    composing this value does not deliver or grant that authority.
    """

    installation_id: str
    workspace_id: str
    runtime_authority: RuntimeAuthorityReference
    runtime_access: RuntimeAuthorityAccessDelivery
    cpk_product: ProductDescriptorDocument
    postgres_product: ProductDescriptorDocument
    secrets_product: ProductDescriptorDocument
    control_credential: SecretReference
    postgres_password: SecretReference
    custody_root_key: SecretReference
    provider_credentials_document: SecretReference
    provider_client_credential: SecretReference
    workspace_grants: tuple[WorkspaceGrant, ...]
    provider_endpoint_ref: SecretProviderEndpointReference
    provider_bootstrap_credential_ref: SecretReference
    ingress: ExternalInstallationIngress | NamedPublicIngress
    connector_product: ProductDescriptorDocument | None

    def __post_init__(self) -> None:
        if (not isinstance(self.installation_id, str) or len(self.installation_id) > 48
                or not _INSTALLATION_ID.fullmatch(self.installation_id)):
            raise ValueError("installation identity must be a bounded Docker alias prefix")
        if not isinstance(self.workspace_id, str) or not _WORKSPACE_ID.fullmatch(self.workspace_id):
            raise ValueError("installation workspace must be a bounded identifier")
        if not isinstance(self.runtime_authority, RuntimeAuthorityReference):
            raise TypeError("installation requires an explicit runtime authority reference")
        if not isinstance(self.runtime_access, RuntimeAuthorityAccessDelivery):
            raise TypeError("installation requires explicit runtime access delivery")
        if self.runtime_access.delivery_kind is not RuntimeAuthorityAccessDeliveryKind.LOCAL_DOCKER_SOCKET_MOUNT:
            raise ValueError("installation currently supports local Docker socket delivery")
        for reference in (self.control_credential, self.postgres_password,
                          self.custody_root_key, self.provider_credentials_document,
                          self.provider_client_credential, self.provider_bootstrap_credential_ref):
            if not isinstance(reference, SecretReference):
                raise TypeError("installation credential inputs must be SecretReference values")
        if not isinstance(self.provider_endpoint_ref, SecretProviderEndpointReference):
            raise TypeError("installation provider endpoint must be an opaque reference")
        _workspace_grants_json(self.workspace_grants)
        if isinstance(self.ingress, NamedPublicIngress):
            if self.ingress.target != PublicIngressTarget(self.cpk_node_id, "http-api"):
                raise ValueError("installation ingress must target its CPK HTTP provider")
            if self.ingress.connector_node_id in (self.cpk_node_id, self.postgres_node_id, self.secrets_node_id):
                raise ValueError("installation connector identity must be distinct")
            _selected_product(self.connector_product, "cloudflared-connector")
        elif isinstance(self.ingress, ExternalInstallationIngress):
            if self.connector_product is not None:
                raise ValueError("external installation ingress must not claim a connector")
        else:
            raise TypeError("installation requires explicit external or named ingress")
        _selected_product(self.cpk_product, "cpk-server-docker-cloudflare")
        _selected_product(self.postgres_product, "postgres-server")
        _selected_product(self.secrets_product, "secrets-server")

    @property
    def cpk_node_id(self) -> str:
        return f"{self.installation_id}-cpk"

    @property
    def postgres_node_id(self) -> str:
        return f"{self.installation_id}-postgres"

    @property
    def secrets_node_id(self) -> str:
        return f"{self.installation_id}-secrets"


def compose_docker_cpk_installation(installation: DockerCpkInstallation) -> DeploymentTopology:
    """Declare existing product contracts and return an ordinary topology tree."""
    if not isinstance(installation, DockerCpkInstallation):
        raise TypeError("composition requires DockerCpkInstallation")
    postgres = _postgres_variant(installation)
    cpk = _cpk_variant(installation, postgres)
    secrets = _secrets_variant(installation)
    children = [
        instantiate_product(product, node_id, ProductInstanceConfiguration.from_contract(product.runtime_contract))
        for product, node_id in ((postgres, installation.postgres_node_id),
                                 (secrets, installation.secrets_node_id),
                                 (cpk, installation.cpk_node_id))
    ]
    public_ingresses = ()
    if isinstance(installation.ingress, NamedPublicIngress):
        connector = _selected_product(installation.connector_product, "cloudflared-connector")
        children.append(instantiate_product(connector, installation.ingress.connector_node_id,
                        ProductInstanceConfiguration.from_contract(connector.runtime_contract)))
        public_ingresses = (installation.ingress,)
    children.extend(SocketConnection(installation.postgres_node_id, "postgres",
                    installation.cpk_node_id, requirement) for requirement in _STORES)
    return DeploymentTopology(
        installation.workspace_id,
        DockerRuntime(runtime_id=f"{installation.installation_id}-docker",
                      network_name=f"cpk-{installation.workspace_id}-{installation.installation_id}",
                      authority_ref=installation.runtime_authority, children=tuple(children)),
        public_ingresses=public_ingresses,
    )


def _cpk_variant(value: DockerCpkInstallation, postgres: ContainerServerProduct) -> ContainerServerProduct:
    base = value.cpk_product.product
    contract = base.runtime_contract
    if set(contract.sockets.requirement_names()) != set(_STORES):
        raise ValueError("CPK installation requires all four PostgreSQL store sockets")
    postgres_environment = {item.name: item.value for item in postgres.runtime_contract.public_environment}
    environment = {item.name: item for item in contract.public_environment}
    additions = {
        "CPK_CONTROL_AUTH_VERIFIER": "static-development",
        "CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON": _workspace_grants_json(value.workspace_grants),
        "CPK_MATERIAL_PROVIDER_ROUTES_JSON": _json({
            value.provider_endpoint_ref.reference_id: f"http://{value.secrets_node_id}:8081"}),
        "CPK_MATERIAL_PROVIDER_BOOTSTRAP_FILES_JSON": _json({
            value.provider_bootstrap_credential_ref.reference_id: _PROVIDER_CLIENT_FILE}),
        "PGUSER": postgres_environment["POSTGRES_USER"],
        "PGDATABASE": postgres_environment["POSTGRES_DB"],
    }
    environment.update({name: PublicStaticEnvironmentBinding(name, item) for name, item in additions.items()})
    contract = replace(contract, public_environment=tuple(environment.values()), secret_deliveries=(
        SecretEnvironmentDelivery("PGPASSWORD", value.postgres_password, SecretUseIntent.POSTGRES_PASSWORD),
        SecretEnvironmentDelivery("CPK_CONTROL_AUTH_STATIC_CREDENTIAL", value.control_credential,
                                  SecretUseIntent.APPLICATION_CONTROL_TOKEN),
        SecretFileDelivery(_PROVIDER_CLIENT_FILE, value.provider_client_credential,
                           SecretUseIntent.APPLICATION_CONTROL_TOKEN),
    ))
    return _variant(value.cpk_product, "cpk", contract)


def _postgres_variant(value: DockerCpkInstallation) -> ContainerServerProduct:
    base = value.postgres_product.product
    contract = base.runtime_contract
    environment = {item.name: item.value for item in contract.public_environment}
    checks = []
    for check in contract.verification.checks:
        if isinstance(check, PostgresQueryCheck) and check.authentication is not None:
            if (check.authentication.database != environment.get("POSTGRES_DB")
                    or check.authentication.username != environment.get("POSTGRES_USER")):
                raise ValueError("PostgreSQL verification must match its declared database and username")
            checks.append(replace(check, authentication=replace(check.authentication,
                          password_reference=value.postgres_password)))
        else:
            raise ValueError("installation requires password-authenticated PostgreSQL verification")
    if not checks:
        raise ValueError("installation requires PostgreSQL verification")
    contract = replace(contract, verification=replace(contract.verification, checks=tuple(checks)),
                       secret_deliveries=(SecretEnvironmentDelivery("POSTGRES_PASSWORD",
                                          value.postgres_password, SecretUseIntent.POSTGRES_PASSWORD),))
    return _variant(value.postgres_product, "postgres", contract)


def _secrets_variant(value: DockerCpkInstallation) -> ContainerServerProduct:
    contract = replace(value.secrets_product.product.runtime_contract, secret_deliveries=(
        SecretFileDelivery("/run/secrets/cpk-secrets/master.key", value.custody_root_key,
                           SecretUseIntent.SECRETS_CUSTODY_ROOT_KEY,
                           path_binding=SecretFilePathBinding("CPK_SECRETS_MASTER_KEY_FILE")),
        SecretFileDelivery("/run/secrets/cpk-secrets/credentials.json", value.provider_credentials_document,
                           SecretUseIntent.SECRETS_PROVIDER_CREDENTIALS_DOCUMENT,
                           path_binding=SecretFilePathBinding("CPK_SECRETS_CREDENTIALS_FILE")),
    ))
    return _variant(value.secrets_product, "secrets", contract)


def _variant(base: ProductDescriptorDocument, role: str, contract: ProductRuntimeContract) -> ContainerServerProduct:
    digest = hashlib.sha256(_json({
        "base_descriptor_sha256": base.content_digest,
        "runtime_contract": ProductRuntimeContractCodec().encode(contract),
    }).encode("utf-8")).hexdigest()
    return replace(base.product, identity=ProductIdentity(base.product.identity.namespace,
                   f"{role}-installation-{digest}", base.product.identity.contract_revision),
                   runtime_contract=contract)


def _selected_product(document: ProductDescriptorDocument | None, name: str) -> ContainerServerProduct:
    if not isinstance(document, ProductDescriptorDocument):
        raise TypeError("installation requires selected product descriptor documents")
    if document.product.identity.name != name:
        raise ValueError("installation selected an incompatible product contract")
    if ProductDescriptorCodec().encode_document(document.product).content != document.content:
        raise ValueError("installation product document must match its canonical contract")
    contract = document.product.runtime_contract
    expected_ports = {
        "cpk-server-docker-cloudflare": {"http-api": 8080, "mcp": 8080},
        "postgres-server": {"postgres": 5432},
        "secrets-server": {"control": 8081},
        "cloudflared-connector": {},
    }[name]
    if {port.provider_socket: port.container_port for port in contract.provider_ports} != expected_ports:
        raise ValueError("installation product provider ports do not match its process contract")
    expected_mounts = {
        "cpk-server-docker-cloudflare": {},
        "postgres-server": {"postgres-data": "/var/lib/postgresql/data"},
        "secrets-server": {"provider-data": "/var/lib/cpk-secrets"},
        "cloudflared-connector": {},
    }[name]
    if {mount.resource_id: mount.target_path for mount in contract.retained_data_mounts} != expected_mounts:
        raise ValueError("installation product retained mounts do not match its process contract")
    if {item.resource_id: item.persistence for item in contract.lifecycle.data} != {
        resource_id: ResourcePersistence.RETAINED for resource_id in expected_mounts
    }:
        raise ValueError("installation product data must retain the declared resources")
    expected_secret = {"cpk-server-docker-cloudflare": "PGPASSWORD",
                       "postgres-server": "POSTGRES_PASSWORD"}.get(name)
    if expected_secret is None:
        compatible_deliveries = not contract.secret_deliveries
    else:
        compatible_deliveries = (len(contract.secret_deliveries) == 1
            and isinstance(contract.secret_deliveries[0], SecretEnvironmentDelivery)
            and contract.secret_deliveries[0].environment_name == expected_secret
            and contract.secret_deliveries[0].intent is SecretUseIntent.POSTGRES_PASSWORD)
    if not compatible_deliveries:
        raise ValueError("installation requires the base product secret delivery contract")
    return document.product


def _workspace_grants_json(grants: tuple[WorkspaceGrant, ...]) -> str:
    if not isinstance(grants, tuple) or not 1 <= len(grants) <= 64:
        raise ValueError("installation requires explicit exact-workspace grants")
    result = {}
    for grant in grants:
        if not isinstance(grant, WorkspaceGrant):
            raise TypeError("installation grants must be WorkspaceGrant values")
        if (grant.workspace_id == "*" or not _WORKSPACE_ID.fullmatch(grant.workspace_id)
                or not grant.scopes or grant.workspace_id in result):
            raise ValueError("installation grants must name unique exact workspaces and closed scopes")
        result[grant.workspace_id] = [scope.value for scope in grant.scopes]
    return _json(result)


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
