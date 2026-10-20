# `test_receiver_authoring.py`

The focused #238 tests build real Core deployment graphs and the local gateway's
real transit, wrapper, and route artifacts. They prove default-random fresh
identity sharing across Y's wrapper and G's route, exact retention of X and G
trust, omitted versus explicit-empty route semantics, exact pending lineage,
and fixed refusal for fresh gateways, current conflicts, and unresolved scopes.
They also cover variable-only verifier selection, legal uppercase/numeric Core
coordinates, opaque pending draft IDs, and exact context/request fence mismatch
refusal before key reads or identity generation.

The client tests prove `0600` artifact publication, authored journal profile,
byte-identical lost-response/restart replay, no callback or owner-read
regeneration, original-source drift refusal, and missing/corrupt artifact
refusal before a second dispatch. CLI tests preserve the closed group grammar.
The first-dispatch callback observes both the immutable artifact and pending
journal at the transport boundary, while injected preparation failure proves no
prepare dispatch occurs.
The import-isolation test also keeps the lightweight profile/bootstrap path
usable when the optional receiver-authoring Core surface is not installed.

Servers #245 strengthens complete authoring scenarios to retain self+X in A/C
and self+X+Y in B. The actual product self-health selector consumes every document;
it must return the retained gateway receiver. Separate registered source-product
scenarios compile real Gateway/Hello contracts and either another Hello or
Secrets. Core materialization supplies the exact same-runtime endpoint and each
product's declared port; Servers authoring copies those endpoints into explicit
route intents. Common own-health selection must agree with Y's authored target
and actual declaration. This is pure source composition using never-executed
image descriptors, not deployment, current graph advancement or saga evidence.
Omitted routes preserve bytes; the existing explicit-empty law remains tested.

#237's real HTTP witness exposed a production response-shape bug masked by the
scripted fixture. The fixture now uses the selected Operations
`FocusedDetailReadModel(...).descriptor()` rather than inventing nested `payload`.
A focused valid-flat response case proves planning succeeds, generates exactly
one receiver identity and preserves the source file. Missing/null/list/text fields
and a nested-only legacy response refuse before receiver identity/prepare dispatch.
The existing complete persist-before-send/lost-response/restart/no-reselection
law runs against that same owner-shaped response without weakened assertions.

Target commit `efcdd751` precedes the production fix. These new unit regressions
were not separately executed red: the maintained runner has no focused mode and
AGENTS forbids ad-hoc containers. North explicitly accepted actual joined run
`38136777213` as causal red and released one ordinary corrected CI instead of a
duplicate full red cycle. Collection/setup failures are not claimed as this red.

Independent review caught an initially dedented extraction that would break zero
introductions. A retained-only client case now verifies successful preparation
with no verifier read or fresh identity allocation, unchanged selected artifact
values, and unchanged source bytes. This complements the existing pure pending
law by exercising the actual client branch. The faulty candidate was not executed.

S1 #249 strengthens the retained-only client case with an ordinary public JSON
application artifact. Preparation must preserve that desired application content
alongside the exact retained wrapper, without a verifier read, identity allocation,
or source-file rewrite. This exercises authoring only, not process replacement.

Servers #253 target checkpoint adds six owner tests for explicit current-receiver
verifier refresh: only the selected wrapper changes; normalized equality retains
valid noncanonical bytes and original source digest; unresolved/pending/conflicting
scopes and foreign bindings/missing verifier families refuse; the client publishes
private exact preparation before dispatch and reconstructed retry does not reread
keys/context or regenerate receiver identity; corrupt preparation refuses; CLI
selection is explicit and rejects duplicates. Existing ordinary-retention and
other authoring laws remain unchanged. These tests use the same real Core values,
owner-shaped public read fixture and journal as the established suite. The initial
public-intent assertion makes absent functionality an explicit test failure rather
than a collection error. This source checkpoint precedes implementation and is
unvalidated until the unchanged owning gate; it is not runtime installation proof.

Kepler's target review adds one mixed authoring law before workflow implementation:
a current health receiver refresh plus a disjoint variable receiver introduction
must request the union of all three public purposes, then install only each
receiver declaration's families. Only the introduced identity is allocated.
This uses the existing graph_variable and public transport fixture and proves
client authoring composition, not Core acceptance of a mixed deployment.
It is a review-strengthened target; no separate executed red is claimed for it.
#253 pre-execution review found that duplicate PEM material under a new key ID
violates Core's within-family fingerprint uniqueness law. The positive overlap
fixture now generates a distinct isolated public key using its existing
cryptography setup. This corrects deeper target setup; it does not change the
recorded missing-interface causal red or claim those deeper assertions ran red.
#253 implementation run39038829926 reached all 407 CPK tests with two failures
in the new whole-graph assertions: their raw fixture artifact tuple order differed
from Core's canonical graph-file order. The two input graphs now pass through
the public Core codec before authoring, as the client graph-file boundary does.
Whole-graph equality and exact wrapper bytes/descriptor/source-digest assertions
remain unchanged; noncanonical wrapper JSON remains embedded verbatim. Five
other refresh targets passed. No later installed Docker stage ran in that failure.
# Servers #254 client declaration authoring

Six new owner tests cover changed declaration plus explicit route composition,
exact identity/verifier/slot preservation, strict ordinary-retained refusal,
semantic no-op bytes/provenance, missing workload/self-route groups, conflicting
or noncurrent scopes, forged current bindings, health-only/readiness limits,
CLI input and immutable preparation before send. Lost-response reconstruction
reuses exact coupled bytes without identity generation or verifier reads; source
drift and corrupted preparation stop redispatch. These are client laws, not
installed Docker or public admission evidence. Existing Core/O5 tests own full
peer-route/alias/origin preservation and supported product-pair admission.
Normal owning gate evidence is pending for this source checkpoint.

The first #254 owning run39074052519 reached413 CPK tests and failed four
assertions: two stale composition coordinates, no-op fixture ordering, and the
new changed-source assertion. Input graphs are now codec-normalized before
transformation, preserving exact output comparisons. Core's artifact constructor
immediately derives source_digest from changed content when given None; the test
checks that fresh digest and its difference from original provenance. No source
behavior changed; these are fixture premises, not target-red proof. Later runtime
phases were unreached and corrected-head owning evidence remains pending.

## Pending #280 pre-instantiation targets

New targets use real generated public verifier material and an empty authoring
context without constructing a graph. They require the fresh preparation API to
produce genuine typed/codec-valid product material, honor owner coordinate
grammars, and refuse malformed identity/context/declaration/verifiers, current
scope and non-null pending drafts with bounded candidate-free errors. The
existing current/pending/mixed, collision, retained-byte and journal/restart laws
remain unchanged.

The composition target prepares each real artifact before its own ordinary
catalogue instantiation. A never-executed source descriptor fixture supplies one
immutable catalogue identity; compiled nodes preserve its original descriptor
digest and OCI reference while payloads differ. This is no publication or live
claim. Missing required material remains a Core refusal.

The new public helper/factory names are resolved inside test bodies. Their
callable assertions are interface availability checks; if they fail, subsequent
semantic assertions have not run and earn no semantic-red credit. No production
placeholder or shim was added. Targets are prepared but unexecuted.

## #280 source implementation checkpoint

The helper and product factories now exist. The target checkpoint's ordinary
run stopped at the root generator omission, so these semantic targets still
have no executed result. The existing two-instance target additionally imports
the shipped parameterized example and requires the same compiled graph. This
strengthens example maintenance without removing any original material,
provenance or missing-slot assertion. Full ordinary green validation is pending.
