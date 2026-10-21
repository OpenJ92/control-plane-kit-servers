# Explicit managed-health startup

Servers #294 adds opt-in source process configuration. Set
`CPK_MANAGED_HEALTH=docker-unix-v1` and
`CPK_MANAGED_HEALTH_CONFIGURATION_FILE=/etc/cpk/managed-health.json` alongside
the ordinary server, control receiver, stores and provider configuration.
The mode requires an execution-capable process, exactly Docker runtime dispatch,
and provider-backed product material with valid endpoint/credential declarations.
The unrelated gateway-probe command signer is not required.

Absent mode or exact `disabled` preserves the existing configuration. In that
case the configuration-file variable must be absent. Empty/unknown modes,
missing files and invalid enabled configuration stop startup; there is no
fallback. Programmatic callers may supply `managed_health_process`, or retain
the existing `managed_health` bootstrap, but cannot supply both.

## Complete fixture-derived input

The reviewed target fixture constructs the complete document below from actual
canonical product documents. This is the authoring shape exercised by
`test_managed_health_configuration.py` in the normal owning Docker suite;
it is not an alternate runner or a deployment command. `NativeMaterial`
constructs synthetic topology/material and ephemeral test keys. Its documents
are fixtures, not admitted Operations history or qualified live images.

```python
import json
from managed_native_material import NativeMaterial

world = NativeMaterial()
raw = json.dumps({
    "schema": "cpk-server.managed-health.v1",
    "docker": {
        "socket_path": "/var/run/startup-private.sock",
        "request_timeout": 5.0,
    },
    "scopes": [{
        "workspace_id": "workspace-a",
        "runtime_id": "docker",
        "authority_ref": world.authority.authority_ref.reference_id,
    }],
    "gateway_documents": [
        world.authored.documents["gateway"].content.decode("utf-8"),
    ],
    "native_product_document": world.document.content.decode("utf-8"),
}).encode("utf-8")
```

For real startup, an operator supplies reviewed canonical documents matching the
registered products and graph, and an explicitly approved local socket/scope.
Document contents are JSON strings, not file paths. The outer schema has exactly
the keys shown, accepts 1–64 unique scope triples and 1–64 distinct gateway
product references, and is limited to 1 MiB. Existing owners validate socket
policy, identifiers, canonical product content and gateway transit slots.
Canonical native content alone does not prove native product shape or readiness.

## Startup and operation

Pure validation runs before schema mutation or provider construction in both
environment startup and direct `create_app`. The provider registry validates
typed references, endpoint URLs and absolute credential paths without reading
credentials. The same policy object then configures execution, reconciliation
and native observation. Managed-health and native selection share the same
selector. Clients remain acquired and closed by the accepted per-call owners;
no shared live client or shutdown registry is added.

Native freshness gets a timezone-aware UTC datetime clock. Operations keeps its
existing string clock and owns sessions, result/history folding and retries.
Scope bindings select capability, not authorization. Current authority, signed
public routing and secret authorization remain required. Fixed local mode
inherits the Interpreter's remote-TLS refusal. It supplies no private gateway
placement, so an entire plan requiring local readiness remains unsupported.

The file is opened once with NOFOLLOW/CLOEXEC/NONBLOCK, checked as a bounded
regular file and closed on all exits. NOFOLLOW covers the final component;
ancestor directories must be trusted. Paths and content are absent from fixed
errors. No extra ownership/mode policy or total read deadline is promised.
Configuration changes require restart.

## Evidence and delivery limits

Reviewed targets at786bc11 produced exactly16 intended missing-interface
assertions and zero errors in run39628908931;491 prior CPK tests passed, and
later suite stages were not reached. Kepler accepted that causal red at
[#294 comment6320231060](https://github.com/OpenJ92/control-plane-kit-servers/issues/294#issuecomment-6320231060).
SOURCE PASS6320460778 covered4ec7c06. Its full owner run39631252315 passed26
policy tests, then stopped at integrity checks: five source `except: pass`
redaction handlers were rejected (products is also a test root). No application
test or later witness was reached. The correction constructs the fixed failure
in each handler and raises it afterward, preserving context-free redaction.
The policy, runner and reviewed targets are unchanged. Corrected source review
and full owning green remain pending; deeper fixtures are not claimed green.

This format is not yet delivered by the closed root launcher or installation
schema. Image publication, live grandparent/child acceptance and provider
cleanup remain separately governed. The original grandparent, tunnel, DNS and
protected token are retained.
