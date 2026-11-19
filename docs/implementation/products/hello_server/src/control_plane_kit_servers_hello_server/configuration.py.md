Source: [configuration.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/configuration.py).

Hello now consumes the actual Core ReceiverNodeControlConfiguration and its
closed workload-node-control-configuration.v2 codec. Installed identity contains
workspace, runtime, node, socket and receiver ID; caller authored/projection
context belongs to requests. There is no product configuration DTO, old-profile
fallback, private wire parser or issuer inferred from a request. Product policy
accepts exactly hello_control_declaration() or its readiness-only counterpart,
with V2/internal/no variables unchanged and readiness always declared. The
default factory remains both-health. Core validates the full
configuration, required purpose-indexed verifier families and bounded public keys.

Decode, artifact and startup failures retain the existing fixed, detached product
error. BaseException is not caught. The SDK load_wrapper_configuration reads the
explicit CPK_WRAPPER_CONFIGURATION_FILE slot: absolute regular non-symlink 0444
file, at most 65536 bytes, one opened descriptor and stable metadata. The import
is deferred to the reader; pure configuration/contract imports start no host.
Parsing and the local file snapshot do not establish current authorization.

The product artifact retains its ID, path, JSON media and 0444 mode. Its renderer
uses Core's actual codec and rechecks product declaration policy. Source contracts
add the common environment binding to that artifact path while preserving existing
sockets, ports, requirements, capabilities and other runtime facts. #241 deliberately
removes Hello's duplicate native checks from the maintained source contract;
the declared SDK liveness/readiness surface remains the health obligation.
Historical published descriptors and images are unchanged. CPK's three variants
retain their existing complete database requirements and process settings; Hello
keeps dependency defaults/readiness; router and multiplexer declare liveness only.

#269 derives control_surfaces from the validated artifact's selected declaration,
not the default factory. Thus artifact, contract, capabilities and credential
declaration identity stay aligned for both supported values. The host and actual
dependency-readiness callback are unchanged. No generic policy framework or
SDK protocol is added.

Reviewed target tests retain malformed/duplicate/foreign-scope and detached-error
laws, opened-file bounds/refusals, full source-contract comparisons and pure import.
These source changes require the unchanged whole Servers and paired Interpreters
gates; authored fixtures and dependency selection are not executed acceptance.
No secret resolution, new durable state, provider effect or authority store exists
in this module. Selected-artifact admission and lifecycle production retain their
existing owners.
