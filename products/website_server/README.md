# Managed website — first packaging/lifecycle slice

Decision: Servers #190 comment6671725082. Source base c029dbaf; reuse selected Web immutable OCI as build input. One container supervises Node's existing /app/server/main.mjs and the SDK management listener, exposing http8080 and control8000 on one website node. No accepted graph is changed.

## Law cards and source dry run

New laws from #190: the actual entrypoint serves the selected website, rejects unauthenticated management calls, terminates/reaps Node after SIGTERM or management failure, exits after Node loss, and cannot retain readiness across a child generation. Existing PostgreSQL process.py and Cloudflare coordinator/managed/entrypoint laws govern fail-closed configuration, SDK routing/auth, child process ownership and bounded shutdown.

Interface: product-owned runtime contract and exact control declaration/configuration validation; PID1 runs a single Node generation and one SDK host. Node command is fixed. No caller-supplied process or health URL is supported. Each new coordinator has fresh health state. No automatic child restart or configuration reload.

Initial readiness is UNKNOWN while Node is alive and UNHEALTHY after stop/exit. Startup asset-manifest verification and independent expected-origin inputs are pending owner contracts. The wrapper therefore never reports positive readiness in this slice. Process liveness is distinct from serving/content readiness.

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
