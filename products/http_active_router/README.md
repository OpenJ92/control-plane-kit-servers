# Active HTTP router

The router selects `ACTIVE_TARGET_URL` once at startup. Ordinary requests retain
method, path/query, body and application headers; Host, Connection and
Content-Length are rebuilt for the upstream. Redirects remain disabled, upstream
calls use a five-second timeout, successful responses are limited to 1 MiB and
HTTP-error response reads are capped. Generic failures use fixed text. Request
body sizes and whole-server concurrency are not globally bounded by these limits.

`/health/live` is the existing public local liveness response. `/health/ready`
is ordinary forwarded traffic. Neither is a new upstream-readiness assertion.
The authenticated SDK surface reserves `/__control` before forwarding:

- `/__control/capabilities` exposes the fixed declaration to static-read authority.
- `/__control/health/liveness` reports local process liveness to health-read authority.
- `/__control/health/readiness` is undeclared and cannot become a healthy result.
- Unknown reserved paths, including `/__control/health/ready`, stay in SDK dispatch.

Successful and denied control requests never forward their credentials upstream.
Application Authorization headers outside the reserved namespace retain their
existing forwarding semantics. There is no readiness callback, upstream probe,
variable, target-switching command or replay store.

## Startup configuration

Wrapped source requires a trusted public configuration file at
`/etc/cpk/router/control.json` before binding the listener. The product-local
`configuration` module defines `RouterControlConfiguration`,
`router_control_configuration_artifact(config)` and
`router_source_runtime_contract(artifact)`. These use actual Core values and
separate SDK static-read/health-read public-key snapshots. The source contract
preserves the active requirement, internal port 8000 and historical single
five-attempt `/health/live` verification policy.

The closed `router-control-configuration.v1` document contains target,
runtime_id, the fixed V2 declaration, surface_read and health_read. Each trust
family contains issuer and 1–16 public keys; audiences derive from the local
target. Unknown/duplicate members, malformed trust/locality and files beyond
65,536 bytes fail closed with fixed errors. No private key or bearer token
belongs in this file. The file reader checks the opened regular descriptor,
rejects final symlinks and does not block on FIFOs. Its parent directory and
producer delivery must be trusted; parsing does not prove provenance.

Production `PORT` must be 8000. Explicit standalone `RouterSettings` ports and
injected loopback addresses support local composition/tests; changing an input
mapping after construction cannot change the selected target. The process owns
bind, activate, serve and final socket closure. The SDK owns protocol/authentication,
and runs no separate listener or supervisor.

## Evidence boundary

The Dockerfile installs the canonically pinned SDK `[verification]` extra and
runs as UID 10003. It embeds no default trust. Source contracts and owning tests
do not qualify a new OCI image: the historical descriptor/catalogue/image
coordinates remain unchanged. Candidate qualification belongs to Servers #191;
authorized identity production and artifact delivery belong to Core #1821 and
Interpreters #149. No provider state or durable history is mutated by these
receiver factories. Use the repository's Docker-backed `./test.sh` under its
concrete gate release; do not invent a separate router execution harness.
