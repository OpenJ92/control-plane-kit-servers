Source: [live_wrapper_artifacts.py](../../../../../products/cpk_local_gateway/tests/live_wrapper_artifacts.py).

#191 reuses the existing numeric-bootstrap daemon/network/resource ledger and
current gateway control fixtures for an actual Hello/gateway artifact pair. The
ordinary package tests receive no Docker socket. This joined artifact check adds
no topology orchestration, Operations service, registry or provider implementation.

The same bounded socket routine always checks current source-built image IDs and,
when the explicit published-digest tuple is selected, additionally checks A and B
against the exact cached private GHCR references. Source mode checks run labels
and records the actual native build platform; it does not claim RepoDigest proof.
Published mode requires the exact existing product repositories, actual matching
RepoDigests, IDs and linux/amd64. Cache misses never trigger a pull. The outer
fixture verifies A/B have different actual IDs; A is expected to lack the visible
attribution, B to contain it under the same configuration. Registry credentials
stay in the authorized producer; the controller creates its own empty Docker
config before constructing the SDK. The socket still grants daemon authority,
so this remains only the existing isolated test composition.

Existing product constructors and gateway fixture signing helpers generate
receiver configuration, selected routes and current-time V2 requests. Actual
containers use default image launch/user and read-only public configuration
mounts, without host-port publication. Assertions cover the independent business
response, exact capabilities, liveness/readiness, missing/wrong-purpose/wrong-
receiver refusal, signed gateway-to-Hello readiness and unknown-target denial.
Missing/malformed configuration must terminate startup; actual process UID is
checked. Package-owned negative matrices remain in their existing tests.

The caller's ledger records each public volume and container before dependent
effects. Each pair retires its own exact containers to free aliases for the next
pair; the outer existing cleanup verifies absence and removes all volumes/helper
containers, including on failure. Shared/preloaded images are retained; only the
outer run-labelled source tags are removed by the normal shell fixture. No CPK
compensation, native connectivity, public ingress or #251 update is claimed.

The bounded result now includes the validated input image references and current
daemon ID alongside actual image IDs/platforms. Published qualification evidence
must correlate the captured execution IDs with linked manifest/config publication
records and the workflow preload daemon. No equality between differently typed
digests is inferred.

#269 takes an explicit selected Hello health tuple, defaulting to both health
kinds for unchanged historical A/B calls. Every selected kind is actually read;
readiness-only additionally requires undeclared liveness and prior-declaration
credential refusal. Gateway both-health and signed readiness-transit assertions
remain. Each result includes the selected Hello declaration kinds and installed
configuration digest alongside actual image identity. Current source Hello
also verifies its actual installed SDK/Core archive provenance; historical
published images retain their original provenance meaning. No pull or producer
effect occurs in this fixture.

#254 permits an explicit expected Hello source revision for the newly published
family artifact. The actual image label must match, and its actual installed
Core/SDK archive provenance is checked against its fixed publication tuple. Historical
published A/B calls retain their existing provenance behavior. Bounded observation
now includes the observed source label, checked runtime UID and installed package
URLs (or null when that historical check is not selected). Actual RepoDigest,
image/platform, default startup, public mounts and signed controls remain required;
the caller also binds execution identity to the independently verified producer's
manifest/config coordinates.

The #254 accepted dependency adoption exposed a shared-expectation defect before
published qualification: source-built and published-family paths previously
required the same historical tuple. `_require_hello_provenance` now selects the
current canonical build coordinates for source-built mode and fixed Core9861/SDKd4e7
for the immutable published family. Both retain exact dictionary equality;
expectations are never inferred from observed container metadata. Existing
optional historical A/B calls still omit this check as before. The two mode
regression tests reject cross-use, partial/extra/substituted entries and unknown
mode. They prove selection/refusal; the original owning Docker gate must still
prove actual installed provenance, sockets and cleanup. No coupled scenario,
image/source identity, UID, runtime or authority changes accompany the repair.

#191 applies the shared fixed-artifact proof whenever a published reference
matches the fixed tuple, including through optional inputs. Genuine extra
references retain their original checks without a fixed-config claim. The
numeric family caller supplies captured Hello/gateway execution IDs; both
declaration launches must still match those IDs before any effects. No registry
credentials, lookup/pull, backend classification or source-built rule changes.
