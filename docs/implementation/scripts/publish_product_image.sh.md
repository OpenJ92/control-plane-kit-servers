Source: [publish_product_image.sh](../../../scripts/publish_product_image.sh).

The existing closed producer cases retain their build/push/catalogue guidance.
The additional counter-witness case selects only the example Dockerfile, builds
explicit Linux/amd64, checks platform/UID10008 before push and reports genuine
post-push digest/image metadata. Its guidance records a witness on the governing
issue rather than updating production catalogue coordinates. Existing manual
workflow dispatch and package-write authority are unchanged; adding a case does
not authorize dispatch or upload.

For counter, capture the inspected built image ID before push and require the
tag still names it afterward. Select RepoDigests by the exact requested
repository prefix and require one canonical SHA256 reference. Missing or multiple
matches refuse; array ordering is not repository identity. The output associates
that exact reference with the captured image ID. This is producer metadata, not
a substitute for actual pulled-by-digest qualification.

The selection itself is delegated to `select_repository_digest.sh`, a pure
stdin-data helper exercised by the existing owning package suite. Image
inspection, push and built-ID correlation remain in this producer.

The producer rebuilds from selected source, so an earlier local/CI startup image
ID cannot identify its output. Publication approval must name reviewed source,
SDK/Core/base/dependencies, startup evidence, platform, exact destination/tag and
verified access/visibility, with actual pulled-digest qualification afterward.
No manifest digest is claimed before push. No credentials enter image/evidence.

The private counter publication repair separates product identity from storage:
`counter-witness` still builds the same Counter Dockerfile but its pure closed
destination helper permits only an existing `cpk-server` package and dedicated
`counter-witness-264-<source-prefix>` tag. The prefix must match the actual Git
checkout. Other product cases retain their destinations. Workflow inputs enter
through step environment variables and quoted shell arguments, never direct
expression interpolation in shell source.

The provider-read guard requires package13950177, private visibility and the
expected repository association before build, immediately before push, and after
push. Complete version pagination must establish tag absence before the effect.
Afterward it correlates the actual digest/tag with one version and records its
complete tag set. API/auth/pagination errors and false predicates fail closed;
there is no new credential, visibility change, registry cleanup or retry.
Actual workflow-token access is unproven until its real execution. These checks
are not an atomic transaction with GitHub push.

Never delete the shared package. Any separately approved version cleanup must
recheck exact ownership and the complete tag set, refusing unrelated tags or
ambiguous ownership. The unintended public counter package16002678 is a separate
incident and grants no authority over private package13950177. The counter
remains a witness, never a production cpk-server catalogue image.
