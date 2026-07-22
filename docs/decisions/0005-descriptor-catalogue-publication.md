# 0005 Descriptor Catalogue And Publication Artifacts

Status: Accepted

Issue: #653

Decision:

Define the server repository catalogue as strict publication metadata for
completed server products. The catalogue records product identity, owner
directory, descriptor path, descriptor digest, source commit, image reference,
image digest, and completed status. It does not import product implementation
modules and it does not define product semantics that belong in
`control-plane-kit-core` descriptors.

The editable source is `catalogue/products.json`. The installable package also
contains an empty `control_plane_kit_servers/catalogue.json` so
`load_catalogue()` remains lightweight and usable from an installed wheel before
any product completes. Publication is deterministic through
`scripts/publish_catalogue.py`, which writes sorted JSON and a sha256 sidecar.

Consequences:

- Only completed product declarations may appear in the catalogue.
- Duplicate product identities fail closed.
- Unknown catalogue or product keys fail closed.
- Descriptor, source, and image digest association is explicit.
- Catalogue loading performs JSON parsing only; no product code, process code,
  network call, or image inspection executes.
- cpk-server remains ordinary external product data.
- Hello remains the first ordinary reusable product proof when its issue opens.

No product implementation enters #653.
