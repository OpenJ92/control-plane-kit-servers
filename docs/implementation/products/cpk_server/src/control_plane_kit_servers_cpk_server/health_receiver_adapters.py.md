Source: [health_receiver_adapters.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/health_receiver_adapters.py).

select_own_health_configuration accepts public Operations HealthReceiverSelection
and returns actual Core ReceiverNodeControlConfiguration. It reconstructs canonical
selection provenance, selects the declared common slot through Core's public
selector, requires the selected slot to agree, then decodes the selected bytes
through that same selector/codec. Workspace/runtime/node/socket must match the
independent selection; declaration must match the descriptor surface. Descriptor
defaults identify a slot, never replace selected trust. Authored/projection caller
context is deliberately absent from installed receiver identity.

health_receiver_decoders is transit-only. Exact supplied gateway documents bind
the existing GatewayHealthReceiverDecoder to its fixed artifact slot/profile.
It projects actual configured keys, issuer, purpose and workspace/node/runtime
into the existing Operations GatewayHealthReceiverTrust. That limited DTO does
not prove receiver-ID/socket; full identity stays in common own configuration and
gateway transit/relay/request comparison. No per-product own decoder, replacement
trust DTO, new registry or production private Operations import remains.

select_gateway_self_health_binding still validates all three selected artifacts,
shared authored/projection/graph-side/product provenance, canonical V2 transit
advertisement/socket and own readiness declaration. Actual product codecs require
full gateway target equality; exactly one alias binding must match full own target
and declaration. It returns internal origin material, not an HTTP/history receipt.

Expected codec refusals become fixed detached HealthReceiverTrustError; unrelated
programmer/owner failures retain identity. No I/O, clock, key resolution, signing,
current authority decision, retry or durable history is introduced. Tests join the
actual accepted Operations coverage owner to real SDK/gateway verification and
preserve selected A/B/AB keys, original graph sides, provenance and refusal laws.
Standalone packaging/production observer activation remains issue181; this pure
selection change neither installs receivers nor qualifies published images.
