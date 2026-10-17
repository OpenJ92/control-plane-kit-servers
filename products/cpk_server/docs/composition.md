# cpk-server Composition Root

#813 creates only the process-composition surface for `cpk-server`. It consumes
`control_plane_kit_core.operations.CpkServerEntrypointHandoffContract` and binds
it to a product-local configuration and process-state model.

This is not the HTTP/MCP server implementation, Dockerfile, OCI image, or
completed product descriptor. Those belong to later EXTRACT.F issues.

## Installation topology

See [Shared Docker installation value](installation.md) for the pure CPK +
PostgreSQL + Secrets topology consumed by future bootstrap and public clients.

### HTTP host preparation (Servers199)

The standard FastAPI host registers each literal Core operator prefix (currently
/workspaces), including its exact and descendant paths. The unchanged neutral
boundary owns route matching, authentication, bounded payload/query decoding and
service dispatch. Exact legacy health/MCP handlers retain precedence; literal
fallthroughs and application-only framework404/405 projection preserve prior
unknown-route, method and slash responses. Decoded __control paths keep actual
SDK/framework responses in composition tests. The root wildcard is removed.

Root and CPK source builds install the canonical SDK[fastapi] dependency. This
prepares hosting without enabling production control routes or changing schema
startup or receiving inputs. The dependent Servers200 child owns that integration.

### Required CPK health receiver (Servers200)

Current source requires trusted `/etc/cpk/cpk-server/control.json`. The product
`control_configuration` module owns `CpkControlConfiguration`, its closed codec,
actual JSON/0444 artifact renderer and `CpkSourceVariant` contract factory for
all three CPK variants. Authorized producers supply the exact target/runtime and
separate static/health issuers/public keys. Parsing alone does not prove producer
provenance; private signing keys are never a receiving input.

`create_app(config, verifier, control=control)` admits that value and installs the
real SDK on the199 host before existing Operations schema/service construction.
It returns only a fully initialized app. Static control reads and liveness are
separately authenticated on http-api8080; liveness is local process availability,
with no mutable variables or readiness callback. Legacy /health/ready reports
configuration only. Existing HTTP/MCP auth, history and all variant topology and
verification fields are preserved. Main requires8080 and the fixed file.

The ordinary source-image smoke selects wrapped-source, generates ephemeral
synthetic public config and240-second read grants inside the existing test image,
and verifies authenticated/denied SDK reads before legacy checks. The historical
published-baseline profile remains distinct. Producer delivery (Core1821 and
Interpreters149), immutable OCI qualification (Servers191), and public acceptance
remain separate work; source configuration does not advance catalogue images.
