# Product topology authoring through MCP

Isolated source qualification for Servers #417/#408 and CPK #2093. The named
cohort, database harness and thin standard MCP bindings passed the owning gate
at `5adb6f117ba92de87b831af6b9dc8b4626743521`. Production dependency
selection is unchanged. Discovery
remains at `8407d3e49841d55eab28d4cf1d44cd0b11f754cb`; its separate draft PR
publication boundary remains in effect.

## Qualified result

The owning Docker gate terminated **exit 0**, with **224 reported tests in 29
batches**: 214 support/source/preservation checks and all ten PostgreSQL-backed
SDK cases. Both SDK eras saved exactly two source products and one edge, then
read the actual receipt's exact revision through a fresh client and HTTP. Both
product pins, runtime membership, environment binding, graph/action truth and
redaction matched; both workspace pointers remained unchanged.

All six post-completion response-loss cases passed the exact-marker, one-send,
one-owner-dispatch and durable-row assertions. Lost start stopped before save;
lost save remained unknown; known receipt plus lost readback allowed a fresh
exact read without another write. Both refusal cases matched HTTP for malformed
input, stale commitment, foreign workspace/pin and current revoked edit access.
All ten schemas and the owned test container, PostgreSQL container, private
network and outer source context have verified cleanup.

Evidence log SHA256:
`1b2ad6e7c47a0259d26d39761f2d4b9f82040f51912ed3392f229e35cf186ced`.
Build-recorded immutable image used by both test phases:
`sha256:787319593a3fccbaaff0919044d3c446b1bbc5e328d871240c7ea6efab7a9404`.
Core/Operations candidate is
`e4bc1275aa3378ecc4e8c32c7872d3f0a4a2ef0c`; the remaining complete cohort
is recorded below and in `products/cpk_server/topology-authoring-cohort.json`.

This proves the named candidate/source boundary. Historical default and frozen
grandparent selections were not separately rerun at this implementation head;
their pins are unchanged, and the named gate includes all existing preservation
checks and the restricted four-read profile. Hosted/full-package and installed
adoption remain separate. No image publication, installation credential,
selection, approval or deployment is included. Independent terminal review is
pending; source failure history below is retained.

## Selected source and qualification

The grandparent selection in `products/cpk_server/grandparent-cohort.json` and
`scripts/test_cohort.py` freezes Core
`f56bb5c4cfde76764d39c5377d4270c5b23c3ba1` and Operations
`70154b6698e101159326b08646f2dba90dda87cd`. The former is an ancestor of the
latter. CPK #2092 merge `d964fc5d2b5dc31ddb6d9b2fd0de60e8a2ac3675`
diverges from this selected lineage; it cannot replace both pins without
preserving the selected readiness, managed verification, and sampling behavior.
CPK #2093 owns the combined revision. After Meridian's source-preservation,
full Core and focused Operations review, North released candidate
`e4bc1275aa3378ecc4e8c32c7872d3f0a4a2ef0c` as X for isolated Servers
qualification. Hosted and installed qualification remain separate.

The default `pyproject.toml` independently selects Core
`7afef43f3d3b981094e37dcb3062b6e3a4f3d674` and Operations
`885513e348b5b9cdb077c9f8804e98d9b2c0e803`. Neither existing selection
contains the authoring contract. A checkout argument to the grandparent gate
selects a repository, not a revision override.

Proposed qualification selection: add a finite named `topology-authoring`
cohort to the owning `./test.sh`, using X for both Core and Operations, while
retaining the historical grandparent mode and manifest unchanged. Keep SDK
`d61b374cb2a23d773c31748f47f88169499298b7`, MCP 2.3.0, Secrets absent,
and Interpreters `e438f6e522ad0a23a7acef460be08690f48b2e17` from retained
export SHA256 `af15d9261cde91e387b2659b489712abbc5579f09ba67ca51350c802552c22e0`
and module tree `97507ed009a5e5c8aa81d280288a2f81ce807835`.

This proposal must preserve exact manifest admission, duplicate/unknown field
refusal, Git export checks, imported module/source and distribution verification,
SDK RECORD checks, dependency closure checks, source-context cleanup evidence,
and every existing grandparent preservation test. No arbitrary pin environment
override, import shim, or fallback package is proposed. Shipping/default pin
adoption is separate from testing the combined source.

## Thin adapter boundary

The source trace follows `client/transport.py:PublicHttpTransport.call` and
`boundary.py:_decode_http_payload`: both branch on the actual HTTP method, so
the owner-declared read-only POST already uses a bounded JSON body. No new HTTP
client or owner-side graph compiler belongs in Servers.

Standard MCP adds only the existing Core parity names:

| Tool | Existing route | Input |
| --- | --- | --- |
| `preview_product_topology` | `read.product-topology-preview` | workspace and closed public recipe |
| `start_operation_session` | `command.operation-session.start` | workspace, title, caller-owned idempotency key |
| `create_desired_topology_draft` | `command.desired-topology-draft.create` | workspace, returned session, title, separate key, product recipe, returned proposal commitment, optional owner receiver expectation |

The first save tool exposes the recipe branch only. Existing HTTP graph callers
remain supported by Operations. The schema mirrors the bounded owner recipe:
one unbound Docker runtime, 1–32 full product references, explicit public static
settings, empty unsupported delivery/configuration arrays, and up to 64 typed
connections. Nested objects reject unknown fields. Operations remains the
authority for semantic validation, current permissions, active pins, receiver
expectations, graph admission, transactions, and replay decisions.

The preview returns the public graph and opaque versioned proposal commitment.
Servers forwards these fields without rebuilding canonical graph bytes or
claiming that the public commitment attests every stored byte. Preview is read
only; start and save are separately marked mutations. The four-tool grandparent
read-only profile still advertises and admits exactly its existing four reads.
No selection, revision rewrite, approval, execution, or deployment tool is added.

## Tests and evidence boundaries

Governing owner tests are CPK
`control-plane-kit-operations/tests/test_product_topology_authoring.py`, the
existing draft catalogue tests, and Core HTTP/parity projection tests. Servers
tests should exercise its own released SDK and actual HTTP host in both SDK
eras, preserving schema, authentication per request, body/output bounds, and
HTTP/MCP equality. Owner rules are reused rather than reimplemented in a fake
store. Existing scripted client tests remain transport evidence only.

The current Servers `--mcp-source-tests` runs with `--network none`; it cannot
run the Operations `DraftCatalogueFixture`, which explicitly requires
`CPK_OPERATIONS_TEST_DATABASE_URL` and disposable PostgreSQL. Complete durable
readback evidence therefore needs an approved extension of the owning Servers
gate with an isolated PostgreSQL fixture. Its design should reuse the owner
schema/unit-of-work fixture, keep database ports unpublished, and create and
clean up only uniquely named owned resources. Do not improvise host execution,
an alternate database, or an ad hoc Docker invocation.
The [isolated PostgreSQL test design](mcp-product-topology-authoring-postgres-tests.md)
specifies the smallest owning-gate extension and its acceptance criteria.

The integrated proof previews two registered products and one edge without
writes, starts once, saves once, and reads exactly the receipt's workspace,
draft, revision and graph. Compare both product identities/digests, runtime
membership, and connection endpoints/protocol. Current and Desired pointers
must remain unchanged. Denials, invalid input and stale proposal refusals must
not publish a revision; owner tests continue to prove transaction/concurrency
semantics.

Loss tests must drop the actual transport response after the application has
handled the request and count dispatched writes. A lost start response stops
before save; a lost save response remains unknown. Assert no SDK/transport
automatic resend and never recover by listing the latest similarly named item.
The adapter does not enforce future operator choices or introduce a workflow
engine. Guidance states the reviewed single-submission procedure; exact reads
can be repeated only when the actual save receipt is known. No new recovery
lookup or local journal is included.

## Decision and handoff

Objects are a public recipe, public preview/commitment, session, saved revision,
and receipt. Operations transforms the recipe into the private compiled graph;
Servers interprets HTTP/MCP framing. The invariant across both surfaces is the
same authorized owner result, preserving receipt and product identities.

Security: new MCP read and mutation exposure requires independent review;
current workspace read/edit checks remain owner-side. Canonical documents and
fixed verification values stay private. No credential, live network, permission,
provider, or runtime change is authorized by this design.

Data/history: only the existing session and draft transactions may mutate
durable state. Save retains the existing action record and append-only revision;
there is no compensation or automatic retry after ambiguity. Exact revision
readback verifies the known result without selecting it. North released combined
candidate X for isolated testing; hosted and installed qualification are
separate. Reviewed apparatus fixes accumulate owned cleanup after partial
creation, use one build-recorded immutable image ID across both phases, and
check exact saved verification/environment shapes.

## Source decision and first runs

The owning run at `4c35c6d28226dc0764a0cc79560c503eb04e9dee` stopped after
26 support tests at the unchanged integrity checker: the DB TestCases used a
non-test-prefixed filename. No candidate build, export or DB resources were
created. This is apparatus failure, not behavioral target-red. Log SHA256:
`2d5bf011de811cf9967e03cc87362278c672cc9ddfa123075f2e29921b15628f`.

After Meridian reviewed normal `test_*.py` discovery in the product-local
`postgres_tests` root, the owning run at
`a3958bc43b0cc5d1ae4670401f818cd4a0805302` reached intended target-red:
214 support/source/preservation checks passed, followed by eight real PG/SDK
cases reporting missing standard authoring tools. Actual SDK TaskGroup errors
wrap those same assertions, not fixture/import errors. The eight schema drops,
test/PG containers, private network and outer source context all have verified
cleanup. Log SHA256:
`58c2061d3979a45f15076317e4a653b5433817f9d90770afb60c439b14234688`.
The build-recorded immutable image was
`sha256:2da19ae5914ca47b4bc74cb4be1c26d974fdaa26f6b7c4a364e21b00906438bd`.

Chosen implementation adds only the owner-declared preview read and existing
session-start/draft-create parity bindings. Closed nested schemas expose the
supported public recipe branch, not raw compiled graphs, confidential delivery
or arbitrary route forwarding. Owner presence in Core metadata controls
advertisement; older cohorts retain their tools and G4 stays four reads. The
single-submission caller flow uses conservative non-idempotent tool hints;
Operations' actual replay/idempotency laws remain unchanged.

The original eight targets remain, with one additional refusal case per era
(ten database cases total) for malformed input, stale commitment, foreign
workspace/pins and revoked edit authority, compared with HTTP. The optional
receiver expectation uses the existing owner's closed five-field shape. No save,
fresh exact readback or actual SDK loss behavior has passed yet. Green and
independent source review are the next evidence; this document does not claim
installed acceptance or release authority.

The first green attempt at `4ba4be83faa5b86735eaae4c9f92054d1de96716`
passed all 214 prior checks, then failed all ten DB cases in the newly added
foreign-product setup: ordinary JSON was sent to Core's strict canonical
document decoder. No MCP authoring call occurred. All ten schemas and owned
containers/network/context were cleaned up. Log SHA256:
`375ff41aaab5a6438f94299a2afb86335747ef183f17a44acc392bcdff5213bd`.
The fixture correction decodes the actual canonical source document, replaces
its product identity as a typed value, and calls Core's canonical encoder.
The decoder, assertions, production code and admitted cohort are unchanged.

At corrected `0b428b9210eb810471b7df27a6ca0ebde6553e75`, both SDK eras
passed actual two-node save and fresh receipt-backed readback, including HTTP
comparison, exact graph/pins/runtime/edge/redaction, independent durable truth,
and unchanged pointers. Both refusal cases also passed. The overall gate still
exited 1: six injected-loss errors surfaced at SDK context teardown outside the
fixture's call-only catch. All ten schema/container/network/context cleanups
were verified. Log SHA256:
`06372d1e11214c9e470c8d5cc7f467462f8fff40a748456195135e9a2d80ad98`.
The next fixture-only correction follows existing
`test_standard_mcp_planning.py` across the entire SDK context using a dedicated
injected exception marker. Unrelated errors propagate; received tool results
cannot masquerade as transport loss. The original durable/send-count assertions
and fresh read from a known receipt remain required. Full green is still pending.
