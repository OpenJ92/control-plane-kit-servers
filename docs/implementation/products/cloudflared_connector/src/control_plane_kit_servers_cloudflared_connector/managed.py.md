# Managed connector configuration and health

Source: [managed.py](../../../../../../products/cloudflared_connector/src/control_plane_kit_servers_cloudflared_connector/managed.py).

Servers #188 composes the common Core receiving configuration and SDK HTTP host
for the synthesized connector's control:8000 provider. The artifact factory and
source-contract factory independently revalidate the exact V2 declaration with
both liveness/readiness and no variables. Contract construction validates the
artifact slot/path/media/mode plus the scoped owner-read-only tunnel-token file
and TUNNEL_TOKEN_FILE binding. There is no native listening provider, retained
storage, public ingress, custom auth decoder or historical descriptor rewrite.

ConnectorHealth observes native process liveness through a supplied local callback
and uses the existing fixed-loopback reader for connection readiness. A nonblocking
probe lock admits at most one read; contention is unknown. Native death and stop
are checked after success or exception, so a late read cannot conceal observed
shutdown. Exceptions yield unknown without candidate/error content. The reader's
existing two-second transport bound remains its owner; no arbitrary probe URL or
new polling service is introduced. Native-alive callback must be a quick local
process observation in the later coordinator, not provider I/O.

create_control_server validates before constructing/binding a socket and uses the
SDK's configuration, verifier setup, protected routes and lifecycle. Non-control
GETs return empty404; request logging is suppressed. The caller owns serve/stop;
bind failure closes the created socket. Ephemeral loopback addresses and injected
clock are package-test host inputs, not deployment configuration.

Kepler reviewed causal targets at0897a7b. This source checkpoint is not yet green.
It implements only configuration/health/SDK composition. Process supervision,
entrypoint, signal/exit guarantees, new OCI, actual stop witness and artifact
qualification remain separate outstanding #188 work. Existing readiness.py and
historical image/descriptor remain unchanged. No provider or credential mutation.

## #280 declaration and actual material

`control_declaration()` exposes the existing pure product surface.
`declared_runtime_contract()` requires the fixed JSON/read-only control file,
with the existing provider/environment/capability/health advertisement and no
concrete default or direct token delivery. It uses the explicitly adopted
accepted Core tuple; no old-Core fallback is promised.

`source_runtime_contract(artifact, token_delivery)` still independently validates
genuine actual V2 configuration, exact slot/surface and owner-read-only token
purpose/path binding. After validation it uses the declared shape with the
requirement discharged into the actual artifact and token delivery. This keeps
one product declaration while preserving the actual-source contract boundary.
No historical native descriptor or image is relabeled. SDK startup/auth and
native process behavior are unchanged.

The parameterized cpk-server example renders actual material before each ordinary
product instance. Generated ingress activation still owns durable token material;
this declaration does not create or resolve secrets. Source review and the full
ordinary gate remain pending; #284/#188 live acceptance is separate.
