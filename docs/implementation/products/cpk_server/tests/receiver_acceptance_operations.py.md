Source: [receiver_acceptance_operations.py](../../../../../products/cpk_server/tests/receiver_acceptance_operations.py).

Issue #1912 public Operations composition. The helper installs the existing
Operations schema in one disposable, grammar-restricted PostgreSQL namespace,
constructs the actual CPK application services over that namespace, and drops
the namespace on exit. Teardown verifies `to_regnamespace` is null; it does not
claim cleanup from a local flag or an unverified `DROP` request.

The #237 pending-baseline prerequisite also uses the actual
`DesiredTopologyDraftCommandService`, wired into `cpk_server_services` with the
same unit of work, clock and ID factory. Both create and select share this owner;
workspace/session and authoring-context reads retain their existing service
composition. The sixth #237 run exposed this previously omitted optional service.
This is test application wiring, not a new production service or a change to #1912
behavior, which does not call draft routes.

S1 #249 can opt into `ObservedEffectStart` through `start_failure_observer`.
The wrapper forwards the original command to the actual service, returns the
identical result, and observes only a raised ordinary start error before the
coordinator sanitizes it. It re-raises that same exception even if the diagnostic
fails. Health-start calls pass through unchanged. Default #1912 composition has
no observer. This is test-only visibility, not owner behavior or result repair.
The initial diagnostic run was rejected by the existing integrity check for an
`except: pass` branch. That branch now explicitly raises the original owner error,
as the existing HTTP diagnostic boundary does; no integrity waiver is added.

`register_material` admits only the authored witness material through public
command routes: three product documents, local-Docker authority, health,
Cloudflare and generated-secret providers, the Cloudflare API reference, two
purpose-specific health-key references and delegation keys, both activations,
and the named zone authority. Provider namespaces, exact health-signing intents,
key IDs, issuer, private references, activation continuity and generated-provider
registration identity are checked from returned public descriptors. Ephemeral
private key bytes remain behind the injected resolver and never enter payloads.

Each A, B, C and teardown transition reads current truth, prepares one desired
Core graph, uses the required ordinary or destructive approval scope, admits,
claims, starts and executes through the public application, then advances current
through the public lifecycle route. No event, attempt, pointer, acceptance or
retirement row is inserted directly. The factory may be reconstructed while the
schema and injected effect ports persist. Missing replacement receipts, missing
key material, non-success coordinator outcomes and malformed durable projections
stop as `OperationsSequenceError`; the helper does not synthesize recovery.

Immediate command replay compares the original public result with its canonical
replay form: only an existing `replayed` field may change from false to true.
An optional effect snapshot proves replay causes no additional provider dispatch.
The driver also retains a bounded copy of each transition's actual final execute
and advance request/result. `replay_original("a")` reuses those exact requests
after later transitions, reconstructs the application, requires canonical results
and unchanged effect snapshots, and leaves the caller to prove current C and the
original installed receiver identity remain unchanged.

Plan-run and run-event evidence is read through the public paged routes with the
owner's maximum page size of 100 and an explicit bounded page count. Returned
history is evidence for the caller's exact accepted-session, ordering, health and
retirement assertions; this helper does not reinterpret it as a second Operations
state machine. The witness uses named in-memory compute, ingress and transport
ports only for external effects and does not establish production Docker,
Cloudflare, credential custody or live-provider acceptance.

No executable validation was run for this helper tranche; the governing
Docker-backed owning gate and independent review remain pending.

`CoordinatorStopped` is reserved for an actual non-progress/non-completed public
execution response and retains its bounded run/result context. Negative witnesses
must match the expected uncertain disposition and durable attempt; generic
`OperationsSequenceError` does not satisfy an injected-fault test.

The second owning run reached real schema bootstrap and workspace creation, then
stopped at this helper's incorrect string guard. Core's `ProductDescriptorDocument`
contract owns canonical `bytes`; registration now requires bytes and passes them
to JSON decoding without a coercive fallback. No deployment plan/effect had started.

#251 may supply an explicit unique material workspace to the same public
registration helper. The legacy fixture default remains workspace-a. The helper
still checks the material shape and all actual public registration responses;
it does not write stores or fabricate admission records.

#346 adds an exact-boolean `install_current` fixture choice, defaulting to the
existing schema installation. False creates only the fixture-owned empty
namespace so the actual bootstrap schema owner can install it. The same exact
namespace cleanup remains responsible for both paths; this is not a second
schema installer or a change to production transaction semantics.
