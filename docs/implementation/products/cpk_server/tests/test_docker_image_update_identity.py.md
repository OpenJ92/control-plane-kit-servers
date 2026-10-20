Source: [test_docker_image_update_identity.py](../../../../../products/cpk_server/tests/test_docker_image_update_identity.py).

#191 targets the fixed-artifact proof boundary, not Docker store classification.
Original byte hashes bind every fixed manifest reference to its unchanged config
identity. Config-valued observations admit omitted/null or coherent Descriptor;
manifest-valued observations require a coherent non-null Descriptor. Both retain
reference/platform/user/source/entrypoint and applicable Interpreter agreement.

Negatives cover absent/tampered/foreign linkage, wrong metadata or IDs, missing
mandatory Descriptor, and non-null malformed/contradictory digest/media/size/
platform evidence with no weaker fallback. Unknown optional roles cannot enter
the fixed qualifier; additional manual artifacts retain their existing distinct
runtime law and receive no fixed-config qualification claim.

Complete daemon-bound maps copy their inputs, freeze proof values and expose a
separate descriptor. Missing/conflicting/unknown role entries or altered identity
facts refuse. No backend labels, driver-field matrix, registry client or public
production API is introduced. Target imports resolve future implementation at
method invocation, not collection. Run only through the owning Docker `./test.sh`;
no red/green or runtime result is claimed by this target checkpoint.

Three #191 review-correction targets exercise the intended workflow caller
`qualify_preloaded_images(daemon_id=..., image_attrs_by_reference=...,
optional_references=...)`, not only the single-role qualifier. A fixed overlap
whose old optional checks pass but whose Descriptor size contradicts the original
manifest must refuse. A genuine extra keeps exact RepoDigest/Linux-amd64 checks
and appears only in an `additional` report with reference/execution_id/platform,
without invented config proof. Every fixed entry remains mandatory regardless
of the optional selection. The caller returns `fixed` as the complete bound proof
descriptor and `additional` as those bounded extra observations. The workflow's
future metadata-only verifier must invoke this same partition/admission boundary;
testing a disconnected helper or retaining independent selection logic is not
sufficient. Its implementation remains absent in this target-only checkpoint.
