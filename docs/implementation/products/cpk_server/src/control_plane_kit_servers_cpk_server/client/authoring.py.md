# `client/authoring.py`

This module is the pure receiver pre-wire transform. It treats Operations'
qualified context as selection evidence, not admission permission. Every graph
control scope resolves to an exact current artifact, an explicitly qualified
pending artifact, or an explicit fresh introduction. Unrelated context rows are
ignored; conflicting or unresolved selected scopes fail with one bounded public
error.

Workspace, node, and provider-socket values are validated as their nominal Core
graph-reference roles. Pending draft IDs use the existing opaque client
coordinate contract; only gateway target IDs use the gateway product's stricter
lowercase identity grammar.

Fresh identities are allocated before route composition. Product-owned gateway
values consume those resolved targets, complete route replacements are installed,
then exact retained/pending and fresh wrapper slots are installed. Core's graph
codec performs the final validation. Omitted route groups are untouched; explicit
empty groups remove all targets. Initial fresh-gateway trust composition is not
claimed and refuses.

Verifier selection is declaration-derived: every receiver requires surface-read,
variable-bearing surfaces also require control, and health-bearing surfaces also
require health-read. Variable-only surfaces preserve the V1 declaration profile;
health-bearing surfaces preserve V2.

The transform handles public verifier keys and public route origins only. It
does not persist, approve, dispatch, inspect installed state, or hold private key
or credential material.

Servers #253 adds explicit `verifier_refreshes` for qualified current scopes.
The existing target/declaration/artifact binding checks run before refresh.
Duplicate, missing-current, pending and introduction conflicts refuse. Existing
declaration-derived verifier selection and Core normalization compare semantic
families; equality returns the original artifact, including noncanonical bytes
and source digest. A changed family replaces only content and clears its stale
source digest. The artifact slot, target, declaration and other graph values stay
fixed. An omitted refresh retains exact current bytes without key selection.

Servers #254 adds explicit `declaration_updates` for current non-gateway scopes.
Original bytes must match their own current declaration identity, full target
and selected digest before the desired surface is considered. Both declarations
must be V2, health-only and retain readiness; only health reads may differ.
Receiver identity, verifier families and slot remain fixed. Semantic equality
preserves exact bytes/provenance; a change rewrites declaration content and
resets source provenance to the new content digest through Core's artifact
constructor. Ordinary retained authoring remains strict.
Pending/introduction/refresh overlap, duplicate and missing-current updates
refuse. Changed declarations require one explicit route group containing the
workload and gateway self. The client context does not contain the current route
table: Core/Operations own peer, alias, origin and product-pair preservation.
This transform neither fetches more graph truth nor implements another planner.

Servers #245 constructs Core `ReceiverManagementRouteBinding` and
`ReceiverManagementRoutes` directly, then invokes the existing product artifact
factory. Complete examples explicitly include gateway self-health plus X in A/C
and retain those bindings while adding Y in B. Explicit empty authoring remains
valid; the consumer's self-selection requirement is not a universal Core law.

Registered source-product examples obtain origins from the compiled
`node.endpoint(socket).url`, whose Core owner derives the protocol/node/declared
provider port. Same-product Hello X/Y and a separate Hello/Secrets case use the
same common receiving configuration and decoder, without an application registry.
The latter tests ports 8000 and 8081 and differing health declarations. Explicit
caller origins remain configuration, not admission authority: Operations must
independently verify eligible pinned graph and registered-product truth.
