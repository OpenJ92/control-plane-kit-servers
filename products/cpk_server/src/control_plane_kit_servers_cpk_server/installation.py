"""Pure Docker installation composition shared by bootstrap and public clients.

This product-owned bootstrap composition declares existing process inputs. It
does not resolve secrets, admit authority, contact providers, or execute a plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import re
from urllib.parse import urlsplit

from control_plane_kit_core.algebra import DeploymentTopology, DockerRuntime, SocketConnection
from control_plane_kit_core.configuration import ConfigurationArtifact
from control_plane_kit_core.environment import PublicStaticEnvironmentBinding
from control_plane_kit_core.identity import WorkspaceGrant
from control_plane_kit_core.lifecycle import ResourcePersistence
from control_plane_kit_core.products import (
    ContainerServerProduct,
    OciImageReference,
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
from control_plane_kit_core.verification import PostgresPasswordAuthentication, PostgresQueryCheck


_INSTALLATION_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")
_WORKSPACE_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}\Z")
# Match the graph codec's canonical environment order when appending connections.
_STORES = ("activity-history-store", "graph-topology-store", "observer-state-store",
           "workplace-store")
_PROVIDER_CLIENT_FILE = "/run/secrets/cpk-installation/provider-client"
_INVALID_WEBSITE = "installation website configuration is invalid"


@dataclass(frozen=True)
class SingleOperatorControlAuth:
    """Use the installation's operator credential and declared grants."""


@dataclass(frozen=True)
class MultiPrincipalControlAuth:
    """Use the server's existing private principal document format."""

    principals_document: SecretReference

    def __post_init__(self) -> None:
        if not isinstance(self.principals_document, SecretReference):
            raise TypeError("principal document requires a SecretReference")


class ControlAuthCodec:
    """Closed authentication values shared by installation input adapters."""

    def encode(self, value: SingleOperatorControlAuth | MultiPrincipalControlAuth) -> dict:
        if isinstance(value, SingleOperatorControlAuth):
            return {"kind": "single-operator"}
        if isinstance(value, MultiPrincipalControlAuth):
            return {"kind": "multi-principal", "principals_document": value.principals_document.reference_id}
        raise TypeError("unsupported installation control authentication")

    def decode(self, value: dict) -> SingleOperatorControlAuth | MultiPrincipalControlAuth:
        if not isinstance(value, dict):
            raise TypeError("control authentication must be an object")
        if value == {"kind": "single-operator"}:
            return SingleOperatorControlAuth()
        if set(value) == {"kind", "principals_document"} and value["kind"] == "multi-principal":
            return MultiPrincipalControlAuth(SecretReference(value["principals_document"]))
        raise ValueError("invalid installation control authentication")


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


@dataclass(frozen=True, kw_only=True, repr=False)
class DockerCpkWebsite:
    """Explicit website image and exposure intent; upstream comes from the API."""

    image: OciImageReference
    ingress: ExternalInstallationIngress | NamedPublicIngress
    connector_product: ProductDescriptorDocument | None = None

    def __post_init__(self) -> None:
        _website_input(self)


@dataclass(frozen=True, kw_only=True)
class DockerCpkInstallation:
    """Immutable desired values; all credential inputs are unresolved references.

    ``runtime_authority`` selects the enclosing deployment runtime. Separately,
    ``runtime_access`` declares the CPK instance's desired process access to that
    same authority. It must be independently admitted before execution;
    composing this value does not deliver or grant that authority.

    ``workspace_grants`` declares setup requirements. In single-operator mode it
    also configures the verifier; in multi-principal mode only the private
    principal document determines effective authority. ``control_credential``
    remains the separate setup bearer in either mode.
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
    control_auth: SingleOperatorControlAuth | MultiPrincipalControlAuth = SingleOperatorControlAuth()
    managed_health_configuration: ConfigurationArtifact | None = field(default=None, repr=False)
    website: DockerCpkWebsite | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.control_auth, (SingleOperatorControlAuth, MultiPrincipalControlAuth)):
            raise TypeError("installation requires a typed control authentication value")
        if (isinstance(self.control_auth, MultiPrincipalControlAuth)
                and self.control_auth.principals_document == self.control_credential):
            raise ValueError("principal document and setup bearer references must differ")
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
        if self.runtime_access.authority_ref != self.runtime_authority:
            raise ValueError("installation runtime access must match enclosing runtime authority")
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
        configuration = _managed_postgres_configuration(self.postgres_product.product.runtime_contract)
        if configuration is not None:
            target = configuration.target
            if (target.workspace_id.value != self.workspace_id
                    or target.runtime_id.value != self.installation_id + "-docker"
                    or target.node_id.value != self.postgres_node_id
                    or target.provider_socket_name.value != "management"):
                raise ValueError("installation PostgreSQL receiving target is invalid")
        _managed_health_artifact(self)
        _website_parts(self)

    @property
    def cpk_node_id(self) -> str:
        return f"{self.installation_id}-cpk"

    @property
    def postgres_node_id(self) -> str:
        return f"{self.installation_id}-postgres"

    @property
    def secrets_node_id(self) -> str:
        return f"{self.installation_id}-secrets"

    @property
    def website_node_id(self) -> str:
        return f"{self.installation_id}-website"


def compose_docker_cpk_installation(installation: DockerCpkInstallation) -> DeploymentTopology:
    """Declare existing product contracts and return an ordinary topology tree."""
    if not isinstance(installation, DockerCpkInstallation):
        raise TypeError("composition requires DockerCpkInstallation")
    postgres = _postgres_variant(installation)
    cpk = _cpk_variant(installation, postgres)
    secrets = _secrets_variant(installation)
    website_parts = _website_parts(installation)
    children = [
        instantiate_product(product, node_id, ProductInstanceConfiguration.from_contract(product.runtime_contract))
        for product, node_id in ((postgres, installation.postgres_node_id),
                                 (secrets, installation.secrets_node_id))
    ]
    children.append(instantiate_product(cpk, installation.cpk_node_id, replace(
        ProductInstanceConfiguration.from_contract(cpk.runtime_contract),
        runtime_authority_deliveries=(installation.runtime_access,))))
    public_ingresses = ()
    if isinstance(installation.ingress, NamedPublicIngress):
        connector = _selected_product(installation.connector_product, "cloudflared-connector")
        children.append(instantiate_product(connector, installation.ingress.connector_node_id,
                        ProductInstanceConfiguration.from_contract(connector.runtime_contract)))
        public_ingresses = (installation.ingress,)
    if website_parts is not None:
        website, connector = website_parts
        children.append(instantiate_product(website, installation.website_node_id,
                        ProductInstanceConfiguration.from_contract(website.runtime_contract)))
        if connector is not None:
            ingress = installation.website.ingress
            children.append(instantiate_product(connector, ingress.connector_node_id,
                            ProductInstanceConfiguration.from_contract(connector.runtime_contract)))
            public_ingresses += (ingress,)
    children.extend(SocketConnection(installation.postgres_node_id, "postgres",
                    installation.cpk_node_id, requirement) for requirement in _STORES)
    return DeploymentTopology(
        installation.workspace_id,
        DockerRuntime(runtime_id=f"{installation.installation_id}-docker",
                      network_name=f"cpk-{installation.workspace_id}-{installation.installation_id}",
                      authority_ref=installation.runtime_authority, children=tuple(children)),
        public_ingresses=public_ingresses,
    )


def _website_input(value: DockerCpkWebsite) -> tuple[str, ContainerServerProduct | None]:
    """Validate enabled-only inputs using the existing frontend owners."""
    from .client.frontend import _canonical_origin, _selected_frontend_connector

    try:
        if not isinstance(value, DockerCpkWebsite) or not isinstance(value.image, OciImageReference):
            raise ValueError(_INVALID_WEBSITE)
        if isinstance(value.ingress, NamedPublicIngress):
            connector = _selected_frontend_connector(value.connector_product)
            return _canonical_origin("https://" + value.ingress.hostname), connector
        if isinstance(value.ingress, ExternalInstallationIngress) and value.connector_product is None:
            return _canonical_origin(value.ingress.endpoint), None
        raise ValueError(_INVALID_WEBSITE)
    except (ValueError, TypeError, AttributeError, KeyError):
        error = ValueError(_INVALID_WEBSITE)
    # Raise outside the handler: rejected input must not survive as context.
    raise error


def _website_parts(value: DockerCpkInstallation) -> tuple[
    ContainerServerProduct, ContainerServerProduct | None,
] | None:
    if value.website is None:
        return None
    from .client.frontend import _canonical_origin, _selected_frontend_connector, frontend_product

    try:
        origin, connector = _website_input(value.website)
        ingress = value.website.ingress
        if isinstance(value.ingress, NamedPublicIngress) and isinstance(ingress, NamedPublicIngress):
            _selected_frontend_connector(value.connector_product)
            product_ids = {value.cpk_node_id, value.postgres_node_id,
                           value.secrets_node_id, value.website_node_id}
            connector_ids = {value.ingress.connector_node_id, ingress.connector_node_id}
            if (ingress.target != PublicIngressTarget(value.website_node_id, "http")
                    or value.ingress.target != PublicIngressTarget(value.cpk_node_id, "http-api")
                    or len(connector_ids) != 2 or product_ids & connector_ids
                    or ingress.ingress_id == value.ingress.ingress_id):
                raise ValueError(_INVALID_WEBSITE)
            upstream = _canonical_origin("https://" + value.ingress.hostname)
        elif (isinstance(value.ingress, ExternalInstallationIngress)
                and isinstance(ingress, ExternalInstallationIngress)
                and value.connector_product is None):
            upstream = _canonical_origin(value.ingress.endpoint)
        else:
            raise ValueError(_INVALID_WEBSITE)
        # Compare host identity only; preserve both original origin strings.
        if urlsplit(upstream).hostname.removesuffix(".") == urlsplit(origin).hostname.removesuffix("."):
            raise ValueError(_INVALID_WEBSITE)
        return frontend_product(value.website.image, upstream=upstream, port=8080), connector
    except (ValueError, TypeError, AttributeError, KeyError):
        error = ValueError(_INVALID_WEBSITE)
    raise error


def _cpk_variant(value: DockerCpkInstallation, postgres: ContainerServerProduct) -> ContainerServerProduct:
    base = value.cpk_product.product
    contract = base.runtime_contract
    managed_health = _managed_health_artifact(value)
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
    if managed_health is not None:
        additions.update({
            "CPK_MANAGED_HEALTH": "docker-unix-v1",
            "CPK_MANAGED_HEALTH_CONFIGURATION_FILE": managed_health.target_path,
        })
        contract = replace(contract,
            configuration_artifacts=(*contract.configuration_artifacts, managed_health))
    environment.update({name: PublicStaticEnvironmentBinding(name, item) for name, item in additions.items()})
    auth_delivery = SecretEnvironmentDelivery("CPK_CONTROL_AUTH_STATIC_CREDENTIAL", value.control_credential,
                                             SecretUseIntent.APPLICATION_CONTROL_TOKEN)
    if isinstance(value.control_auth, MultiPrincipalControlAuth):
        auth_names = {"CPK_CONTROL_AUTH_STATIC_CREDENTIAL", "CPK_CONTROL_AUTH_STATIC_WORKSPACE_GRANTS_JSON",
                      "CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON"}
        if any(getattr(item, "environment_name", None) in auth_names for item in contract.secret_deliveries):
            raise ValueError("selected product contains incompatible authentication secret delivery")
        for name in auth_names:
            environment.pop(name, None)
        auth_delivery = SecretEnvironmentDelivery("CPK_CONTROL_AUTH_STATIC_PRINCIPALS_JSON",
            value.control_auth.principals_document, SecretUseIntent.APPLICATION_CONTROL_TOKEN)
    contract = replace(contract, public_environment=tuple(environment.values()), secret_deliveries=(
        SecretEnvironmentDelivery("PGPASSWORD", value.postgres_password, SecretUseIntent.POSTGRES_PASSWORD),
        auth_delivery,
        SecretFileDelivery(_PROVIDER_CLIENT_FILE, value.provider_client_credential,
                           SecretUseIntent.APPLICATION_CONTROL_TOKEN),
    ))
    return _variant(value.cpk_product, "cpk", contract)


def _managed_health_artifact(value: DockerCpkInstallation) -> ConfigurationArtifact | None:
    artifact = value.managed_health_configuration
    if artifact is None:
        return None
    # Disabled installation planning must not import optional Docker adapters.
    from .managed_health_configuration import (
        MANAGED_HEALTH_ARTIFACT_ID, MANAGED_HEALTH_CONFIGURATION_PATH,
        _INVALID_INSTALLATION, _managed_health_configuration_from_artifact,
    )
    process = _managed_health_configuration_from_artifact(artifact)
    contract = value.cpk_product.product.runtime_contract
    if (process.local_client_config.socket_path != "/var/run/docker.sock"
            or any(item.name in {"CPK_MANAGED_HEALTH", "CPK_MANAGED_HEALTH_CONFIGURATION_FILE"}
                   for item in contract.public_environment)
            or any(item.artifact_id == MANAGED_HEALTH_ARTIFACT_ID
                   or item.target_path == MANAGED_HEALTH_CONFIGURATION_PATH
                   for item in (*contract.configuration_artifacts, *contract.configuration_requirements))):
        raise ValueError(_INVALID_INSTALLATION)
    return artifact


def _postgres_variant(value: DockerCpkInstallation) -> ContainerServerProduct:
    base = value.postgres_product.product
    contract = base.runtime_contract
    if _managed_postgres_configuration(contract) is not None:
        # The managed source contract advertises signed health. Installation
        # startup additionally requires semantic SQL using the same credential.
        check = PostgresQueryCheck(check_id="installation-postgres-ready", provider_socket="postgres",
            authentication=PostgresPasswordAuthentication("cpk", "cpk", value.postgres_password))
        contract = replace(contract,
            verification=replace(contract.verification, checks=(check,)),
            secret_deliveries=(replace(contract.secret_deliveries[0], reference=value.postgres_password),))
        return _variant(value.postgres_product, "postgres", contract)
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
    if document.product.identity != ProductIdentity("control-plane-kit", name, 1):
        raise ValueError("installation selected an incompatible product contract")
    if ProductDescriptorCodec().encode_document(document.product).content != document.content:
        raise ValueError("installation product document must match its canonical contract")
    contract = document.product.runtime_contract
    if name == "postgres-server" and _managed_postgres_configuration(contract) is not None:
        return document.product
    environment = {item.name: item.value for item in contract.public_environment}
    if name == "cpk-server-docker-cloudflare":
        required_settings = {
            "CPK_SERVER_MODE": "execution-capable",
            "CPK_CONTROL_AUTH_CONFIGURED": "true",
            "CPK_RUNTIME_INTERPRETERS": "docker",
            "CPK_INGRESS_INTERPRETERS": "cloudflare",
            "CPK_PRODUCT_MATERIAL_RESOLVER": "provider",
            "CPK_PORT": "8080",
        }
        if any(environment.get(key) != value for key, value in required_settings.items()):
            raise ValueError("installation CPK product lacks required process settings")
    if name == "postgres-server":
        for key in ("POSTGRES_USER", "POSTGRES_DB"):
            setting = environment.get(key)
            if (not isinstance(setting, str) or not setting.strip()
                    or len(setting.encode("utf-8")) > 63
                    or any(ord(character) < 32 or ord(character) == 127 for character in setting)):
                raise ValueError("installation PostgreSQL identity must be bounded nonempty text")
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


def _managed_postgres_configuration(contract: ProductRuntimeContract):
    """Admit the explicit managed variant without importing it for native roots.

    The PostgreSQL product owns its closed file, socket, data and declaration
    contract. Only the password reference is installation-specific at intake.
    """
    if not any(port.provider_socket == "management" for port in contract.provider_ports):
        return None
    from control_plane_kit_servers_postgres_server.configuration import (
        decode_postgres_control_configuration, postgres_source_runtime_contract,
    )
    if len(contract.configuration_artifacts) != 1 or len(contract.secret_deliveries) != 1:
        raise ValueError("installation managed PostgreSQL contract is invalid")
    artifact = contract.configuration_artifacts[0]
    expected = postgres_source_runtime_contract(artifact)
    expected = replace(expected, secret_deliveries=(replace(expected.secret_deliveries[0],
        reference=contract.secret_deliveries[0].reference),))
    if expected != contract:
        raise ValueError("installation managed PostgreSQL contract is invalid")
    return decode_postgres_control_configuration(artifact.content.encode("utf-8"))


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
