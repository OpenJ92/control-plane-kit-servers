Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This owner interprets desired-topology draft create/revise/select intent
through public HTTP routes. Its catalogue is the server's saved-draft language,
distinct from this package's product publication catalogue. It passes graph
JSON as opaque input for server admission; a successful local decode does not
prove a valid topology, permission grant or deployment plan.

Mutation creates a private catalogue invocation under a per-operation journal
lock before starting an operation session. It records that response, validates
an open session before the first draft dispatch, records the exact draft
request digest, then calls the selected command. Create/revise re-read a
size/hash-bound file; select captures the initial desired graph/projection/
generation fences. Explicit resume preserves those inputs and idempotency keys,
rather than choosing a fresh revision, fence or replacement session.

Once a draft request was recorded, resume does not repeat the fresh-session
open check before replaying that exact request. A completed local receipt
returns without fresh reads. These are public replay-contract assumptions and
historical transport receipts, not proof the current draft head or deployment
still matches. Authorization errors propagate; transport/input evidence
failures retain an attention-required record. Persistence failures can occur
after a server effect and are not rolled back across HTTP.

Response validation binds workspace, selected draft/revision and expected
generation increments, with closed journal shapes and separate start/draft
keys. The record stores file locators and private intent/title data instead of
the graph body; returned projections omit graph/title/raw history fields.
Bounded text and JSON checks are not universal secret detection, and a bounded
opaque next cursor is returned without interpreting its contents.

Read paths project overview, one draft-list page or an exact revision using
operator credentials. Overview checks graph/projection pairs, selection and
workflow relations and allowed next-action scopes, without executing that
action. Reads do not initialize an invocation journal. CatalogueResult is a
bounded receipt/observation, with attention-required exit 4, and supplies no
provider freshness, transaction authority or graph-current advancement.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [products/cpk_server/tests/test_topology_client_catalogue.py](../../../../../../../products/cpk_server/tests/test_topology_client_catalogue.py), [src/control_plane_kit_servers/catalogue.py](../../../../../../../src/control_plane_kit_servers/catalogue.py).
