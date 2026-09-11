Source: [scripts/publish_catalogue.py](../../../scripts/publish_catalogue.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This CLI parses input/output paths and delegates to the shared catalogue publisher, then prints its report. Publishing here means writing local packaged catalogue bytes and checksum, not pushing an OCI image or registering products through a control-plane API. Validation, sorting and output semantics remain in the catalogue owner; keep the wrapper small and use that owner when reviewing changes.

Related source and evidence: [src/control_plane_kit_servers/catalogue.py](../../../src/control_plane_kit_servers/catalogue.py), [tests/test_descriptor_catalogue.py](../../../tests/test_descriptor_catalogue.py), [docs/decisions/0005-descriptor-catalogue-publication.md](../../../docs/decisions/0005-descriptor-catalogue-publication.md).
