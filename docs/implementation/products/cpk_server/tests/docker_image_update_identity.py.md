Source: [docker_image_update_identity.py](../../../../../products/cpk_server/tests/docker_image_update_identity.py).

Test-owned stdlib qualification shared by public image admission, numeric/wrapper
witnesses and the workflow's isolated metadata verifier. No registry client,
Docker call, production API or backend classification is introduced.

`qualify_fixed_image` binds original manifest bytes (at most64KiB) by SHA-256 to
the fixed reference and checks the schema2/config/layer descriptor forms and
unchanged config digest. It requires exact local RepoDigest, Linux/amd64, user,
applicable source/entrypoint and supplied Interpreter-ID agreement. Non-null
Descriptors must match digest/media/original byte size and supplied platform.
Config-valued identity permits omission/null; manifest-valued requires coherent
non-null Descriptor. Contradictions refuse before identity-form selection;
there is no weaker fallback. Immutable proof fields preserve both identities.

`bind_fixed_images` copies and freezes exactly the five roles, validates their
fixed identity fields, and binds them to a bounded daemon ID. Its descriptor is a
fresh separate value, never the mutable backing for the captured expectation.

`qualify_preloaded_images` is the workflow's actual fixed/optional union boundary.
It requires every mandatory reference and fully qualifies fixed overlaps first.
Genuine extra references retain exact repository/digest syntax, RepoDigest and
Linux/amd64 checks; they receive only bounded reference/execution_id/platform
reports. They cannot mint a fixed config claim or replace required observations.

The file CLI accepts one bounded metadata document (at most256KiB) and invokes
that same caller. The workflow runs it network-disabled, socket-free,
credential-free and over readonly mounts. Duplicate JSON keys and malformed
inputs refuse with bounded errors. The trusted Engine observation remains the
runtime source of truth: this does not rehash config blobs/layers, attest an
arbitrary daemon or establish runtime qualification. Sidecars are the reviewed
original fixed manifests, not registry output reconstructed during a witness.
