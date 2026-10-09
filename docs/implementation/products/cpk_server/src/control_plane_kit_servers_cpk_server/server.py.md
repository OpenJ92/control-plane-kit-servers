Source: [server.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py).
Maintain with the process composition and operational ownership boundary.

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

HTTP and MCP host closures await their process boundary handle_async methods.
The shared boundary uses the exact constructed service objects in the actual
Operations application, whose async entrance selects managed execute/reobserve.
No task is detached and no nested event loop is introduced. Synchronous neutral
entrances remain available for existing callers; the hosted routes use the
awaited path. This joins transport to Operations, not the still-separate
managed-health registry/signing/native observer composition under issue181.
