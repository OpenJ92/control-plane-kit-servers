Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This is the CPK image process composition and FastAPI entrypoint. It connects
Core's public language, Operations services/stores and optional Interpreters.
The server does not define the durable deployment, approval, lease, replay or
effect-fold laws; it constructs their owners against the actual package pins.

Environment decoding supports execution-capable mode, explicit runtime/ingress
availability and none/provider/local-development material modes. Availability
does not grant workspace or process runtime authority. All four named store
URLs must be identical at application construction, reflecting one supported
instance database rather than four independently hosted stores. Direct
dataclass construction is not the same validation path.

Static-development authentication supports either a single bounded ASCII
credential plus exact-workspace grants or at most sixteen explicit principals.
Mixed single/multiple settings, duplicate credentials, wildcard workspaces and
unknown scopes/kinds are refused. AUTH_CONFIGURED alone is not a verifier:
main must construct one, and create_app receives it explicitly. Auth parsing
uses ordinary JSON for grants/principals, unlike the duplicate-rejecting
provider registry decoder.

create_app is effectful: _operations_application opens PostgreSQL and calls
the adopted schema installer, committing before service composition. That
installer creates an empty owned namespace or verifies exact current schema/
data under its own transaction/locks; it is not an automatic migration/reset.
A shared UoW factory supplies planning, drafts, authorization-dependent
registration, approval/admission, lifecycle, execution and advancement.
Start/fold/reconciliation services and a runtime observer feed the coordinator.
The adopted service map composes saved preparation internally and retains
unsupported recovery/authorization service roles without disabling request
authentication.

HTTP and MCP delegate to the common boundaries. Health routes are public;
ready reports configuration labels and enabled interpreter names, not fresh
database/provider/target checks. MCP JSON is decoded before boundary dispatch,
and both surfaces buffer request bodies before downstream bounds. This
FastAPI layer does not add a streaming request cap or complete JSON/parser
hardening. Interactive docs/OpenAPI are disabled.

Disabled runtime execution and observation yield explicit unsupported values.
Enabled Docker adapters/observer use separate lazy SDK clients with the
adopted ambient-client configuration; connect_on_init=False postpones Docker
connection, not later provider effects. This module does not attach a shutdown
lifecycle that closes those SDK clients. Workspace authority, secret-use grants,
effect admission and cleanup remain with their owning services/interpreters.

Provider mode builds validated opaque endpoint/credential-file registries and
grant-consuming resolver/custodian objects. It does not read credentials merely
to construct the registry. Cloudflare ingress and the Ed25519 gateway signer
require this mode; the small local-development resolver only type-checks a
grant and looks up its reference in fixture values, relying on its caller's
authorization. Legacy Docker credential environment shortcuts are refused.

Cloudflare adaptation translates Operations authority/resource values and
forwards explicit resolution/custody grants. Gateway dispatch requires an
admitted literal private/public endpoint, constructs the signer/client and
context-specific address policy, and maps selected security/client failures
into bounded evidence. Public DNS validation/resolution and signed transport
remain interpreter-owned. Constructing these adapters or returning an
unsupported result is not proof of live provider safety or completeness.

main binds 0.0.0.0 and disables access logging; deployment owns exposure.
It catches selected configuration/composition errors before app construction.
Schema/app-construction failures and other exceptions are not all covered by
that handler. Credential/material fields are hidden in selected repr values,
but store_endpoints remain in the default configuration repr and can contain
connection secrets. Repr flags, fixed error messages and disabled access logs
are not universal exception/log sanitization. No startup success, health
response or source inspection establishes deployment/restart acceptance.

Related source and evidence: [products/cpk_server/tests/test_current_cpk_server_composition.py](../../../../../../products/cpk_server/tests/test_current_cpk_server_composition.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [pyproject.toml](../../../../../../pyproject.toml), [coordinates/server-products.json](../../../../../../coordinates/server-products.json).
