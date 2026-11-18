Source: [health_receiver_adapters.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/health_receiver_adapters.py).

## #309 required gateway slots

Transit startup binding and route/self declaration checks now use existing Core
`product_configuration_slots`, which projects exact slots from both requirements
and concrete artifacts. The selected actual artifact is still independently
revalidated and decoded; no requirement becomes configuration bytes. Canonical
product references, full graph context, target equality and Operations authority
remain unchanged. The adapter gains no I/O or registry. Owning green is pending.

select_own_health_configuration accepts public Operations HealthReceiverSelection
and returns actual Core ReceiverNodeControlConfiguration. It reconstructs canonical
selection provenance, selects declared structure through Core's public
`select_receiver_node_control_configuration_slot`, requires the selected slot to
agree, then validates selected actual bytes through the unchanged strict V2
artifact selector and codec. Declared payload can be inert `{}`; actual payload
must contain valid receiver configuration. Workspace/runtime/node/socket must match the
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

Servers #245 decodes targets directly with Core `ReceiverManagementRoutesCodec`
and returns a `ReceiverManagementRouteBinding`. Canonical syntax refusals are
translated alongside existing product trust/control failures to the existing
bounded `HealthReceiverTrustError`. Unexpected owner errors still propagate.
Declared slots, full selection context and exact self-target/declaration matching
remain unchanged. No receiver registry or dispatch authority is added.

#280 passes `contract.configuration_requirements` only to the declared-side
common receiver slot selector. A structural required slot can therefore bind
genuine selected actual V2 material. Original selected-product provenance, four
slot fields, strict actual decoding, complete target/surface and independent
selection scope remain mandatory. The actual selector receives no requirements;
missing actual material cannot become a declaration-only success. Gateway
transit parsing/selection is unchanged. This adds no authorization, network or
current-state owner. Full owning validation remains pending.
