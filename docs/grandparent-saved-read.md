# #399 one-batch saved graph verification

This is a separate verification-only entry and launcher. It accepts no switch
argument and mounts no Docker socket. Its helper runs as501:20 with all
capabilities dropped, read-only root, host networking, fixed local HTTP API,
cached installer0d5, bounded resources and logging disabled. The host launcher
checks only exact engine/original name/ID/image/running/port metadata and the
reviewed source/input hashes. It never reads the original environment.

The existing human bearer is loaded once through the installed client file
protections and pinned for all four GETs to127.0.0.1:18163. The API authenticates
it. This batch makes no extra identity/readiness call and does not locally read
the private principal document. Routes are workspace, Desired, exact saved
draft revision1 and that revision's first attempts page at limit10, once each,
without retry, pagination, command routes or client attachment. A failure stops
the batch and returns a nonzero status with only a fixed route/safe category.

The reader verifies the fixed workspace/Current/Desired/draft/revision and both
retained realized projection coordinates. The authored graph IDs are UUIDs;
the projection IDs are the retained `projection-` plus digest coordinates.
Operations701 produces the same Desired pointer in the workspace and separate
Desired read, and both public graph descriptors use its redactor. Compare the
entire returned redacted JSON objects against the owner-redacted public baseline
after JSON projection, including nested JSON types. The baseline is the reviewed
49,118-byte eight-node desired.json, SHA256f3b0f8a2321e521a989c3a8d84e51c7431b1c8e3056c0e4a0a08c7e05a702e2a.
No raw graph, response body or credential is printed or persisted. This proves
only equality of comparable public projections, not private authored bytes.

Attempts reporting names the returned count, limit10 and whether next_cursor is
present. Coverage is first-page-only. An absent cursor is observed page exhaustion,
not a promise of no future attempts or preservation of every history item. Full
page items/cursor remain in the in-memory canonical snapshot. The batch does not
perform a restart or before/after service comparison and cannot earn cutover or
capstone acceptance.

The fresh run is cpk399-gparent-saved-read-20261114-01, with its own host evidence
directory. Existing evidence refuses invocation. Only a confirmed terminal owned
helper is cleaned using exact ownership/cid/labels and residue checks. No service,
network, volume or graph resource is changed or cleaned. Unknown helper outcome
stops without killing or replaying it. Earlier switch attempts remain intact.

Owning offline validation is ./test.sh --grandparent-artifact-source-tests,
using synthetic owner-matched inputs and the actual installed transport, server
query decoder, Operations page/projection values and production reader entry.
No real credential, network, daemon socket, store or live graph enters that suite.
North must relay Meridian PASS before the already conditionally approved one
live batch is released. Final plan/digest are durable issue coordinates; source
and test success alone do not dispatch it.
