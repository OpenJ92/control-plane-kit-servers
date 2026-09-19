# Gateway own control configuration

The product owns `GatewayControlConfiguration`: exact gateway target/runtime,
fixed V2 control-socket declaration with liveness/readiness and no commands,
plus separate actual SDK surface-read and health-read public verifier families.
The public artifact `gateway-control` is JSON0444 at
`/etc/cpk/gateway/control.json`, profile `cpk-gateway-control-configuration.v1`.
Closed decoding bounds input to65536 bytes, rejects duplicate/nonfinite/deep
JSON, validates canonical public Ed25519 keys and the exact declared surface.
Errors retain no candidate material or exception chain; representations redact
configuration. The reader rejects symlinks/nonregular files and uses nonblocking
open plus a bounded read. It resolves no secret and makes no network request.

Artifact admission requires the exact slot/path/media/mode. Startup and the
complete runtime-contract factory require own target workspace/node/runtime to
match the relay's selected workspace/gateway/runtime. Graph revision and key
selection are supplied independently by the parent; parsing does not grant
current authorization. Source artifact and installed trust are not proof of
production provenance or image association.
