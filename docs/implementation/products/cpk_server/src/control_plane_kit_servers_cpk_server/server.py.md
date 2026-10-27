Source: [server.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py).
Maintain with the process composition and operational ownership boundary.

#341 passes the actual configured Operations application into the shared boundary,
preserving its resolver and authority mode instead of extracting its service map.
The MCP host collects at the existing envelope budget and forwards raw bytes to
the boundary, where headers/authentication precede strict JSON decoding. Duplicate
members are therefore not lost in an earlier permissive host parse. This source
slice awaits its owning gate and does not yet configure dynamic factory/startup
or managed invocation composition. The static authority account below remains
the existing production factory behavior until those later changes.

#315 explicitly projects configured static-development principals into a
credential-free ConfiguredPrincipalAuthorizer. Main passes it to create_app,
which forwards it through _operations_application into the shared factory.
Injected verifiers alone never imply policy; create_app's authority defaults
to None. The provider composition adds the thin public-client generator using
its same bootstrap registry/transport and forwards it through effect ports.
No constructor opens provider credential files. Generation needs both ports.
#317 forwards the same existing provider custodian through the optional effect
port; the shared factory enables provision only with independent authority too.
Disabled/local-development custody remains absent. No provider adapter, service
policy or credential format is added. Permission changes require a new
process, with no hot reload or token/session revocation claim. See
[configured authority](../../../../../deployment-input-authority.md).

Servers #294 adds explicit managed_health_process configuration. The environment
wrapper preserves the disabled legacy parser and translates enabled failures to
one fixed, context-free bootstrap error. Both public create_app and private
_operations_application validate before schema/provider work. The extracted
_provider_bootstrap_registry reuses exactly the existing pure registry owner;
resolver, custodian and metadata construction remain at the existing later
boundary. Revalidation of the immutable process input performs no effects.

Enabled composition supplies one exact Unix policy to execution, reconciliation
and native observation, and one selector to managed-health and native selection.
Native receives an aware UTC datetime clock; Operations retains its string clock.
endpoints=None preserves whole-plan refusal for local-required readiness.
Existing disabled/programmatic borrowed behavior and metadata adapter selection
remain. See the [startup format](../../../../managed-health-startup.md).

Run39631801423 caught a disabled-mode eager Docker import in the initial wiring.
Managed process/native imports now occur only in enabled validation/composition
branches; the value annotation is type-checking-only. The existing zero-I/O,
no-Docker-import disabled observer assertion is preserved. All16 new startup
targets passed that run; the remaining full owner gate is still required.

Selected-version composition (#252) adds one typed metadata bridge over the
Interpreter reader and existing provider bootstrap registry. The concrete IO
validates requested workspace/reference/version; the bridge requires the existing
observation's exact reference/version, active status and intended use before
returning Operations metadata. Copied correlation/registration fields associate
the request locally; they are not provider-signed receipts or execution authority.
Errors and representations remain bounded/redacted. No plaintext resolution or
selection registry is introduced.

The shared Operations factory injects this port into DesiredGraphCommandService,
whose accepted preparation/transaction/replay rules remain the owner. Provider
mode explicitly registers the actual Docker execute and execute-with-authority
entrances for selected versions. Passive exact-version observation remains false;
no-provider/local development composition is not selected-consumer fallback.

create_app requires keyword control:ReceiverNodeControlConfiguration. It revalidates the
actual public artifact, builds pure composition and the unstarted standard host,
registers literal public routes, and calls actual SDK install_cpk_wrapper with
the common configuration. The wrapper owns separate instance static/health
verifiers, protected routes and actual host lifespan. Only after installation succeeds
does the existing _operations_application construct schema/services. The HTTP/MCP
closures are bound and app.state assigned before the completed app is returned.
No listener or partial app escapes an admission/schema failure. A test clock is
injectable; production uses integer Unix time.

Existing Operations schema transaction, service selection, auth, request decoding
and history ownership stay intact. SDK liveness returns local HEALTHY only when
this initialized app is serving. It calls no store/provider/service; readiness
is undeclared. Legacy /health/ready remains configuration-only. Main requires the
explicit common receiving file via CPK_WRAPPER_CONFIGURATION_FILE and port8080, creates the complete app before logging that
it will listen, and then starts Uvicorn. This is source behavior; the historical
published image remains separate until candidate qualification/publication.

HTTP uses request.stream with handle_stream_async so route/auth admission precedes
body reads. MCP uses the same neutral collector with a fixed inclusive 1 MiB
envelope before JSON parsing, then awaits its existing handle_async entrance.
Both map only the payload-free overflow exception to fixed 413 and ignore
Content-Length as an acceptance authority. No request.body call remains in these
host closures. SDK wrapper routes keep their own unchanged host behavior.
The shared boundary uses the exact constructed service objects in the actual
Operations application, whose async entrance selects managed execute/reobserve.
No task is detached and no nested event loop is introduced. Synchronous neutral
entrances remain available for existing callers; the hosted routes use the
awaited path. The optional managed-health composition now joins that path through
the explicit #294 startup value; root-launcher delivery and live acceptance
remain separate from this source-process wiring.
