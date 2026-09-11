Source: `tests/test_descriptor_catalogue.py`.
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

[Source](../../../tests/test_descriptor_catalogue.py) owns publication-record validation, declaration provenance fields, deterministic catalogue/checksum output and the rule that catalogue loading does not import product/process code. Temporary publication files are test artifacts; catalogue status `completed` describes accepted declarations, not a live workload observation.

The implementation owner is [catalogue.py](../../../src/control_plane_kit_servers/catalogue.py). Preserve duplicate/incomplete/unknown-record rejection and import isolation without turning the fixture's chosen identifiers into Core laws. Public product registration, deployment planning and provider acceptance are separate boundaries; this suite does not prove them.
