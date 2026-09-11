Source: [products/cpk_server/tests/test_source_live_abort_compensation.py](../../../../../products/cpk_server/tests/test_source_live_abort_compensation.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These unittest cases dynamically import the provider-neutral abort helper and
the source-live controller. They exercise checkpoint files in temporary
directories, injected cleanup callbacks, mocked database/provider/Docker
boundaries and source-text launcher assertions. They do not perform live
compensation or establish that a real provider resource is absent.

The principal laws are checkpoint-before-injected-fault; authoritative EMPTY
transition before emergency dispatch; no fallback after a lost response when
absence is independently established; and non-authoritative/nonzero reporting
when emergency cleanup was needed. RecordingWorkflow exposes the expected
desired-graph fence and selected calls. Missing or contradictory failed-run
evidence must not supply an emergency candidate. The suite separates accepted
successful graph evidence from an exact failed connector effect and selects only
eligible unadvanced resources for emergency dispatch.

Decoder cases reject duplicate resources, oversized/raw authority coordinates,
coerced epochs, noncanonical secret references and invalid provider version
numbers. SQL mocks inspect bounded text projections and ordering; they do not
execute the query or prove database row-count bounds. Failed connector evidence
must identify one start activity and successful event. Docker mocks require the
expected name and every ownership label before stop/remove. Those assertions do
not establish immutable container custody across concurrent name reuse.

The Cloudflare compensator's mocked call order is exact version revocation,
connector stop/remove, DNS deletion, tunnel connection deletion and tunnel
deletion. Injected failures check that later independent stages are still
attempted and bounded stage labels are reported. Revocation evidence requires
each expected version ID in provider audit rows. Selected snapshots, descriptors
and exception tests exclude candidate secret/reference/provider values; this is
not universal redaction of arbitrary callbacks or diagnostic output.

The shell test checks that abort-cleanup precedes fixture removal and that
required selectors/scopes appear in source. It does not assert preservation
after abort-cleanup fails. The actual launcher attempts cleanup and state-root
deletion without an abort-result preservation gate; unrelated shell/filesystem
failure may interrupt that deletion. See the independently confirmed
[custody finding](https://github.com/OpenJ92/control-plane-kit-servers/issues/172#issuecomment-5630579917).
Do not infer a safe live retry or destructive release from these fixture tests.

Selected behavioral navigation was checked against the
[abort helper](../../../scripts/cpk_server_source_live_abort.py.md),
[controller](../../../../../scripts/cpk_server_secret_provider_source_live.py)
and [Cloudflare launcher](../../../scripts/cpk_server_cloudflare_secret_custody_source_live_smoke.sh.md).
This companion is not a full audit of every fixture permutation. Executable
validation belongs to the repository's Docker-backed test suite.
