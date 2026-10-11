Source: [unlisted_controller_host.py](../../../../../products/cpk_server/tests/unlisted_controller_host.py).

Servers #237 source-composition helper. `ControllerHost` owns one
ephemeral IPv4 loopback socket, bounded uvicorn thread, and one private temporary
child beneath a fresh absolute controller state root for credential files and
journal state. The constructor accepts the actual public Operations driver,
retains its operator and worker principals, and creates a distinct approver with
the existing witness-principal helper and both ordinary/destructive approval
scopes. Context exit requests normal server shutdown, closes the exact listener,
waits within a fixed bound and attempts every temporary-file cleanup step.
Cleanup defects are raised and chained to an original startup or body failure
rather than hidden. The affirmative cleanup marker is emitted only after the
thread is stopped, the listener is closed and the private credential/state root
is absent. Access logging is disabled and credential values are never retained
in exchange records or exposed as strings.

The host calls the injected actual Operations application factory and gives its
`services` mapping to the maintained `CpkServerApplicationBoundary`. Authentication
uses `StaticDevelopmentMultiCredentialVerifier` with those exact operator,
approver and worker witness principals. The canonical cpk-server composition,
`CpkServerHttpProcessBoundary`, and `install_operator_http_routes` own route
matching, request decoding, authorization and dispatch. This helper contains no
route translator, trusted-context constructor, accept-all verifier or replacement
Operations behavior.

The yielded host exposes its canonical loopback `endpoint`, real `ClientProfile`,
private credential-file paths and `topology_client()` constructor. All three
client credential roles use distinct ephemeral credentials authenticated as their
explicit principals. The caller supplies the already-composed public driver;
the helper does not widen its operator or worker grants.

`prepare_exchanges` retains at most sixteen actual POST request byte strings and
their completed `command.deployment.prepare` boundary status/body. The host never
drops, changes or fabricates that response. A caller-owned transport wrapper may
invoke the real transport once, discard exactly the first successful prepare
result, and then use the maintained client's pending-request replay path. This
separates lost-response simulation from server execution and recording.

This helper proves only public HTTP/client composition over caller-injected
Operations services. It does not provide live providers, images, production
credentials, listener hardening, TLS, process supervision or provider acceptance.
No host test, alternate gate or CI command was run for this contribution.
