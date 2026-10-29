Please update alongside [publish_product_image.sh](../../../scripts/publish_product_image.sh).

## Managed PostgreSQL (#191)

`postgres-server-managed managed-<source>` selects the managed PostgreSQL recipe
explicitly. The tracked archive, revision/recipe labels, Linux/amd64 and user70:70
are checked; an existing matching-visibility package and absent tag are required before effects,
with actual owning-repository/visibility/tag/digest association checked after the single push. It leaves the
native descriptor unchanged. See [procedure and limits](../../managed-postgres-artifacts.md).

`postgres-server-managed-first` is an explicit first-publication alternative;
the existing selector still refuses package absence. The first selector observes
only the exact package GET's included HTTP response and exit status before build
and before push. Its product policy accepts404 only;200 and all other failures
stop. Package checks bind repository ID/name association and visibility to independently
read owning-repository metadata: public→public or private→private only. Repository
identity/visibility is reread before build/push and after push; drift stops.
Post-push checks bind the package to the owning
repository and recheck candidate fields, including its source label. It creates
the real image directly, never a dummy prerequisite. Owner attestation and
one-attempt authorization are external execution-plan prerequisites, not values
the script invents or authenticates. IDs from private package/version metadata
are not printed. See the same procedure for token wiring and concurrency limits.

## Current CPK/Secrets producer metadata (#191)

These two existing branches gain clean-checkout admission, Linux/amd64, actual
checkout revision label and numeric user10001/10006 checks before push. Captured
image ID must remain identical afterward; the existing exact-repository selector
returns its digest. Output separates producer source, observed platform/user/ID
and digest. It changes no catalogue and does not imply ABI qualification.

Exact source/tag/private destination plus privacy/tag-absence checks remain the
reviewed effect packet. These branches do not inherit Hello's provider visibility
policy automatically. No retry/deletion/visibility repair follows uncertainty.
See [current-root qualification](../../current-root-artifacts.md).

## Hello declaration-family publication (#271)

The Hello branch accepts only the existing repository
`ghcr.io/openj92/control-plane-kit-servers/hello-server`, private package13951244,
and tag `hello-271-<full source commit>`. The pure destination helper requires
owner and package separately before any provider or Docker call. Dirty source
refuses. The metadata guard reads
package identity, repository association, visibility and all version pages before
build and again immediately before push. An existing source tag refuses rather
than overwriting or treating an ambiguous earlier attempt as permission to retry.

The Docker build explicitly selects Linux/amd64 and records the full source
commit as an OCI label. The producer checks platform, configured user `hello`
(Dockerfile creates numeric UID10002), source label, and captures the image ID.
After push the tag must still identify that same image. Inspect output is captured
before the exact-repository selector; missing, malformed or ambiguous RepoDigests
refuse. The provider guard then verifies the exact published digest and unique tag
association while the existing package is still private. Output is evidence of
the publication attempt, not actual pulled-image qualification.

This is not an atomic registry transaction. Concurrent visibility/tag changes
can race these reads; a post-push failure leaves the external outcome uncertain
and stops without retry, deletion, visibility repair or credential changes.
GitHub CLI/page failures must not be masked by a pipe. GH_TOKEN is the existing
workflow token, stays outside Docker and is not a build input. Metadata verification
with that token is unproven until an explicitly authorized producer run.

The obsolete counter-witness producer case is removed. Other existing product
branches remain unchanged; this does not claim equivalent publication safeguards
for every product. Historical Hello descriptor/image coordinates stay immutable.
The generic selector retains its negative laws and is now exercised with Hello.

Any dispatch still needs the concrete approved source/build/tag/destination
packet. Its manifest digest cannot be invented before publication. Qualify the
actual pulled artifact with both accepted declarations, installed dependency
provenance, authentication and cleanup before #254 consumes it. SDK/Core source
commits and Python base are pinned; transitive third-party Python requirements
are not a complete reproducible dependency lock. A rebuild can differ; the final
digest, installed distributions and observed provenance identify its actual output.

## Managed cloudflared (#308)

`cloudflared-connector-managed managed-<source>` explicitly selects the managed producer. The existing `cloudflared-connector` native recipe is unchanged. Set `CPK_MANAGED_RELEASE_RECEIPTS` to a new absolute evidence directory under the reviewed artifact release. The managed producer acquires controller apparatus explicitly, qualifies one exact candidate and retains it; publication is a separate consequential invocation, not released by normal CI.

For CPK/Secrets only, the existing successful push and immutable readback now
also expose public reference/source/image-ID fields through GITHUB_OUTPUT when
running in Actions. This occurs after the existing public publication line and
performs no additional registry operation. The opt-in CPK account step consumes
those actual results in a separate workflow step. A later failure leaves the
publication outcome intact and never authorizes a push retry or rollback.
