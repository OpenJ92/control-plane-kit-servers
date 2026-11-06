# Managed website — first packaging/lifecycle slice

Decision: Servers #190 comment6671725082. Source base c029dbaf; reuse selected Web immutable OCI as build input. One container supervises Node's existing /app/server/main.mjs and the SDK management listener, exposing http8080 and control8000 on one website node. No accepted graph is changed.

## Law cards and source dry run

New laws from #190: the actual entrypoint serves the selected website, rejects unauthenticated management calls, terminates/reaps Node after SIGTERM or management failure, exits after Node loss, and cannot retain readiness across a child generation. Existing PostgreSQL process.py and Cloudflare coordinator/managed/entrypoint laws govern fail-closed configuration, SDK routing/auth, child process ownership and bounded shutdown.

Interface: product-owned runtime contract and exact control declaration/configuration validation; PID1 runs a single Node generation and one SDK host. Node command is fixed. No caller-supplied process or health URL is supported. Each new coordinator has fresh health state. No automatic child restart or configuration reload.

Readiness is UNKNOWN until the owned Node signals successful listening and a valid build-owned index expectation is loaded. The protected callback then compares one bounded local index response. Exact page match is HEALTHY; explicit mismatch is UNHEALTHY; deadline/refusal is UNKNOWN. Stop/exit invalidates the generation. This narrow local-page claim follows Jacob's accepted #190 comment6672106167. Full bundle integrity, independent upstream correctness and public/customer acceptance remain separate.

Tests first target the public configuration/contract and real subprocess entrypoint using synthetic protected configuration, local HTTP and generated test-only signing keys. Source test red precedes implementation. Production qualification and release stay separate. Do not interpret a mock supervisor test as packaged-entrypoint proof.

## Packaging inputs and boundaries

Dockerfile requires WEBSITE_IMAGE to be an independently selected immutable digest reference for an ordinary Web image containing /app/dist, /app/server/main.mjs and Node. It adds pinned SDK/Python without modifying Web's ordinary entrypoint. The selected image content and provenance remain caller-reviewed inputs. Product identity/adoption/publication follow normal owner review.

Runtime receives the existing CPK_WRAPPER_CONFIGURATION_FILE protected configuration and CPK_WEB_UPSTREAM. The accepted expected child origin and qualified manifest have no production delivery contract yet. Neither value is inferred into a positive readiness result.

Security: management uses SDK signed-scope verification and is separate from visitor HTTP. Child environment excludes management configuration/key material. Native output is suppressed; coordinator diagnostics are categorical. No secrets, provider credentials, Docker socket, forwarding of parent auth or new durable truth. Generation-correlated polling and admission are subsequent owner work.

Operational history: SDK supplies protected health responses. This slice emits only a bounded terminal lifecycle category and does not replace Operations history. Shutdown owns only its child process group. No deployment or release is performed.

## First checkpoint validation

Five focused product tests pass in cached Servers SDK runner1758d975: two sockets, one-generation health invalidation, child environment isolation, port collision refusal and real SDK signed-read authorization with UNKNOWN→UNHEALTHY outcomes. Initial red comprised the four absent product-interface tests, collected without collection errors. SDK boundary case was added during implementation review.

The explicit packaged_witness.py uses the default image entrypoint, synthetic generated public verifier configuration and loopback-only visitor/management bindings. It verifies real index and entry JavaScript, management401, visitor rejection of control paths, SIGTERM exit0, unexpected Node exit1, and a fresh replacement container. Its initial malformed test-only receiver identity was corrected before it created a container. No real credential, API or provider request occurs. The script owns/rechecks labels and removes only its newly created containers; it retains images and fixture material.

The new unittest file is collected by the existing scripts/run_all_tests.py::product_test_roots discovery. The explicit Docker witness is a separate packaging proof command documented in its module. It does not replace the full owning test.sh/CI gate before merge. These are source/local evidence only.

Pending: image-qualified asset manifest and independent accepted-origin delivery; a generation-bound positive startup receipt and subsequent receiver/poll composition; selected descriptor/image adoption; normal independent review and owning gate. No source claim of healthy website readiness.

## Review correction and ordinary stop boundary

Meridian identified the wrapper's original eight-second grace as shorter than the selected Web's ten-second upstream deadline and eleven-second drain. The wrapper now allows twelve seconds for Node plus bounded final reap/management shutdown. A fixture-only delayed HTTPS adapter keeps the actual Web main/serving code and produces a nine-second synthetic decision response. The explicit drain witness uses an outer twenty-second test budget and proves only the wrapper's own drain behavior.

The selected Docker interpreter685c8627 stop_container calls Container.stop() with no timeout; the owning Docker SDK documents default ten seconds. The selected container renderer exposes no stop-timeout input, and the Core product lifecycle models retention rather than process grace. An image StopSignal does not set a larger stop timeout. Ordinary StopNode orderly-drain acceptance remains held. Owner choice is a scoped runtime grace contract preserving current Web timing, or a deliberately shorter managed-only Web deadline/drain with a proven total teardown bound. This slice does not change global defaults or silently select the latter policy.

Kepler identified that constructing the SDK host after spawning Node left a brief visitor-startup path before management refusal. Management construction/bind now precedes Popen, the health holder attaches exactly one child, and serving management starts only after attachment. A bind/refusal unit test proves zero Node launches. Child environment filtering prevents accidental inheritance only: Node and wrapper share the same UID/filesystem. Control configuration must carry only the reviewed public verifier material.

The default-entrypoint packaged witness now also makes a synthetic authorized SDK readiness request for every original/replacement and asserts UNKNOWN with request correlation. This is negative generation evidence only; image/manifest/origin-qualified positive readiness remains absent.

## Managed-only timing candidate

Jacob requested evaluating the smaller product-only timing adjustment first. The new product-owned Node entrypoint reuses selected Web createWebServer/parseRuntime with a five-second upstream deadline, 6.5-second whole-response deadline and seven-second drain. The selected ordinary /app/server/main.mjs remains in the image with its original timings. The supervisor gives managed Node eight seconds, then a 0.25-second reap and two 0.25-second management joins. This leaves nominal margin below the normal ten-second Docker stop window.

Visitor tradeoff: slow upstream requests time out sooner than the ordinary website. A decision POST may have committed at CPK before the response is lost or times out. The browser's existing unknown-outcome/check-status path remains required; a timeout must never be displayed as a rejection or cause automatic resubmission.

This candidate supersedes the earlier twelve-second internal-grace proposal for this product only. The earlier nine-second successful response used explicit twenty-second grace and remains wrapper-only historical evidence. The updated fixture exercises both a 4.5-second successful proxy response and a nine-second synthetic response that must time out at five seconds. It invokes the selected DockerSdkClient.stop_container without a timeout override against the label-verified owned container, whose Config.StopTimeout is absent or ten. The controller uses only the existing local test Docker socket; it cannot select an arbitrary target.

SDK7.2.0 low-level creation supports stop_timeout and normal stop uses Config.StopTimeout, but its high-level container-create keyword allowlist does not accept stop_timeout. This is an additional adaptation requirement for any future explicit-grace alternative. Neither Core nor the interpreter is changed here.

## Local page readiness and failed-drain correction

The build records actual selected index length/SHA-256 in /app/website-index.json, outside the served tree, root-owned0444. Missing/untrusted/malformed expectation yields UNKNOWN. The supervisor binds SDK management first, attaches its Node once, and consumes a capped fixed notification from that exact child's private stdout pipe. Managed Node sends it only from the successful visitor listen callback. An identical foreign listener with no owned-child listen signal cannot become eligible.

Each authorized readiness call performs one fixed credential-free loopback GET with one-second absolute/per-read bounds and at most the expected index length plus one byte. It checks status, MIME, length and SHA-256, then rechecks child lifetime. No redirects or healthy cache. Unit tests prove no probe before the owned signal, mismatch/redirect/timeout refusal, expected-file protections and a late match overridden by child exit.

Requested stop now propagates nonzero child.wait status as website_drain_failed. The specific exit1-before-eight-seconds test was red (old supervisor incorrectly returned0) and is green after correction; clean exit0 remains covered.

## Packaged local-page checkpoint and framing hardening

At source9a46f75, the real default OCI entrypoint returned signed HEALTHY for original and replacement generations; a test-only root-owned wrong-digest expectation returned signed UNHEALTHY. A separate already-bound foreign identical-page listener fixture produced43 authorized UNKNOWN responses, then owned Node bind failure and PID1exit1. This proves the owned-listen eligibility boundary independently of matching response bytes. Runtime UID1000 could write neither /app nor the root-owned0444 expectation.

Meridian found contradictory Content-Length/Transfer-Encoding could be accepted by http.client, and a detached close-response socket could evade the watchdog. The corrected probe rejects every Transfer-Encoding, retains the actual transport across getresponse/body, shuts it down at the absolute deadline and rechecks monotonic expiry. The old frozen image returned HEALTHY for the new dual-framing regression; corrected source refuses it. A close/trickle case returns UNKNOWN within1.75s and the next probe succeeds, proving slot release. Expectation loading uses O_NONBLOCK before fstat; a subprocess-bounded FIFO test returns UNKNOWN promptly. Build hashing reads at most MAX_INDEX_BYTES+1. All15 focused product laws passed after this hardening.

No full-bundle, accepted-child-origin, public ingress or customer authentication assertion is implied by local-page HEALTHY. Full owning test.sh/CI and exact-head reviewer clearance are still required before merge.
