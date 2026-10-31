Source: [test_root_account_projection.py](../../../../../products/cpk_server/tests/test_root_account_projection.py).

Seven synthetic ordinary-suite methods cover original/normalized manifest
correspondence, ambiguous index/duplicate-key/refusal, actual config platform/user
and diff-count admission, foreign or altered descriptors and corrupted bytes,
complete membership/hash projection, account ambiguity/size refusal and
symlink/hardlink/path-component refusal. They exercise real parsing, hashing and
descriptor-relative filesystem reads with temporary private fixture files.

Layer bodies are deliberately synthetic: these tests prove correspondence and
account projection, not valid layer unpacking, umoci success, tool provenance,
actual published-image accounts or process identity. No image, tool acquisition,
Docker/provider mutation or host executable validation is performed by this source
preparation. Run through the existing owning Docker suite after source review.

The acquisition connection adds two laws using the same pure owner: exact original
and unique platform selection, and pre-copy descriptor/size refusal with no OCI
layout present. This proves metadata can be admitted before blob acquisition;
it does not prove actual Skopeo, registry authentication, quotas or controller
lifecycle. The original seven methods passed ac144857; these additions are unrun.

The diagnostic correction adds one parameterized method exercising all eight
offline failure boundaries through the real CLI main function with filesystem
and process doubles. It requires the exact fixed refusal/phase record, reserved
exit, no stdout result and no later unpack/account call after an earlier failure.
Private exception canaries cannot enter diagnostics. Every case fails; no
successful unpack or account seal is synthesized as acceptance evidence.

The config-correspondence correction begins with a target-red witness: a
representative Docker-schema2 original configuration includes Docker-only fields,
while the normalized OCI config omits them and uses different serialized bytes.
Both preserve the same account/filesystem-relevant values and layer descriptors.
The real verifier must return separate source/normalized config identities, never
the private source-config content. The fixture stores raw source-config bytes
separately for the proposed descriptor binding. This does not run or reimplement
Skopeo; the maintained source establishes that such a conversion is permitted.
At checkpoint d635171, run40774219942 reached this witness and failed at the
unchanged60a4386 verifier's config digest/size equality check. Independent review
confirmed intended target-red evidence, not a fixture or apparatus failure.

Three additional methods bind actual source config bytes and descriptor size,
reject missing/corrupt/oversized/duplicate-key source input, require both configs
to satisfy the account/filesystem prerequisites, and reject corrupt normalized
bytes or changed/reordered diff IDs. The existing altered-descriptor case may
refuse with a missing-file error because a different normalized config digest is
now valid only when its corresponding verified blob exists. Digest inequality
alone is no longer a refusal. These synthetic checks do not establish the exact
live failure predicate or successful unpack.
