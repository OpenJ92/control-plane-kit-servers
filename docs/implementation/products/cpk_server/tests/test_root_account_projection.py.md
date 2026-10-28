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
