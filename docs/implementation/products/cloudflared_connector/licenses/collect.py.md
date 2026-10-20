# Build-only notice collector

Source: [collect.py](../../../../../products/cloudflared_connector/licenses/collect.py).

The distinct managed Dockerfile calls this product-local collector in a build
stage. It reads the committed manifest and fetches exactly the pinned upstream
commit archive once. There is no revision fallback, retry loop, mutable tag
fetch or runtime network behavior.

Bounds:120second overall traversal deadline checked between operations,
30second download socket timeout,64MiB compressed input,512MiB expanded declared
members,50000members and8MiB per notice. In-flight reads and scheduling are not
claimed to stop at an exact nanosecond deadline.

The collector validates relative paths and manifest uniqueness, scans all source
members for the selected notice names, rejects unexpected/duplicate/link notices,
verifies every Git blob hash, and requires exact inventory equality. It never
extracts the tar archive onto disk; only verified notice bytes are written to the
fixed output root, with read-only file modes. It also retains the exact
manifest. Partial or mismatching input fails the build before runtime-image copy.

This small source collector is separate because embedding the traversal in a
Dockerfile would obscure the validation and license-input review. It is not a
shared downloader/framework or a production entrypoint. No host Python, alternate
gate or standalone collector run was used. Its execution and bundled output
remain for the one normal owning gate after exact source review.
