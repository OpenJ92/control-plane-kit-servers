Source: [control_configuration.py](../../../../../../products/cpk_local_gateway/src/control_plane_kit_servers_cpk_local_gateway/control_configuration.py).

Gateway own configuration is the actual Core ReceiverNodeControlConfiguration,
profile workload-node-control-configuration.v2. Core owns closed wire parsing,
full workspace/runtime/node/socket/receiver-ID identity, declaration and required
purpose-indexed verification families. The product requires its exact control
liveness/readiness declaration and preserves its stricter existing canonical
Ed25519/512-byte public-key check. No old product DTO/parser/profile fallback exists.

The gateway-control artifact retains JSON0444 and /etc/cpk/gateway/control.json.
Actual SDK loading uses CPK_WRAPPER_CONFIGURATION_FILE and enforces an absolute,
regular, non-symlink 0444 file, bounded size and stable opened-file metadata.
Malformed values become the existing fixed detached error; interruption propagates.
Artifact admission revalidates the exact slot and content digest. Own configuration
must match the relay's entire gateway_target, including receiver ID and socket.

No credential supplies installed identity or trust. Parsing grants no current
Operations permission and produces no I/O beyond the explicit loader. Actual
SDK startup verifies the selected public keys; source contracts and historical
image coordinates remain separate evidence. The original obsolete-profile
causal-red fixture remains independent and must now refuse at this real decoder.
