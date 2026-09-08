# #148 revision history packaging — test context

Source-fit packet reviewed by Meridian and Kepler; North released this isolated
feature from the documentation checkpoint of `roadmap/1754-application-readiness`.
Accepted source baseline is `8923679b2b0724c976215c227850ce297c444d7c`; upstream
owner to consume is CPK `73f645d506ad6c2f79cfeff4bc6869a7f4cf6980`.

## Governing laws and source fit

Existing current-composition tests own exact canonical/generated dependency
coordinates, installed Core declarations, imports and one Operations map.
Existing HTTP/MCP boundary tests own credential-before-dispatch, bounded query
grammar, opaque cursor transport and safe errors. Existing image smoke owns
non-root image bootstrap, authenticated public paths and fresh disposable
PostgreSQL composition. They do not own history membership or advancement.

Target tests strengthen that boundary for the two revision preparation/attempt
reads: exact HTTP path, READS role and MCP binding, declared default/max10,
workspace/draft/revision/limit/cursor transport parity, denied credentials and
workspace access before owner/UoW, and bounded malformed arguments. The installed
smoke will create a saved revision through public catalogue commands, compare
empty HTTP/MCP pages and detail presence, and exercise bounded errors. Empty
pages prove installed composition only; nonempty history laws remain upstream.

The existing server composition delegates Core declarations to Operations. No
new server queries, state machine or production boundary change is justified
unless the tests reveal a concrete gap. Canonical CPK coordinate and generated
pyproject/server-image/gateway-Core mirrors must move together; interpreter,
Secrets, published image and product coordinates remain fixed.

## Execution and stops

Next: prepare tests-only bytes for Meridian static review. No source/pin changes
or test invocation before that review. Publish a candid tests-only checkpoint,
then use only ordinary Docker-backed `./test.sh` to establish causal missing
route/coordinate red. After classification, implement the minimal accepted pin
change, review source, and run the same full suite.

Supported image overrides: `CPK_SERVERS_TEST_IMAGE=control-plane-kit-servers-test:148`
and `CPK_SERVER_IMAGE=localhost/control-plane-kit-servers/cpk-server:148`.
Preflight exact project residue before the suite; any unrelated residue or
missing pull/runtime prerequisite is a stop, never permission to prune, repair
shared state, log in, or replace the harness. Fresh suite PostgreSQL is allowed
only at the released validation boundary.

Security/data: authenticated workspace-contained reads, no new owner authority,
provider calls, direct database history seeding, image publication, retained
installation/schema changes, reset/migration/backfill, client workflow or #1774.
The one-MiB owner descriptor bound is not a transport-envelope cap; cursor pages
are not snapshots. Meridian reviews, Kepler integrates, North merges. PR140 is
an explicit dependency before the new roadmap promotes to develop.

This checkpoint is documentation only; diff-check is its validation. All server
behavioral and installed-image evidence remains pending.
