Source: [tests/test_package_metadata.py](../../../tests/test_package_metadata.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks the package metadata against the coordinate input and protects the lightweight catalogue facade. A cold isolated subprocess imports from the supplied source path, loads the expected completed catalogue and checks selected HTTP/process modules were not loaded. Other cases inspect immutable catalogue assembly and selected AST imports.

The subprocess is source-import evidence, not installed-wheel provenance or a running product. The import-name scan is static and selective; it cannot prove arbitrary dynamic effects are impossible. Keep source pins, product record expectations and the facade coordinated without treating the completed catalogue marker as deployment success.

Related source and evidence: [pyproject.toml](../../../pyproject.toml), [src/control_plane_kit_servers/__init__.py](../../../src/control_plane_kit_servers/__init__.py), [src/control_plane_kit_servers/catalogue.py](../../../src/control_plane_kit_servers/catalogue.py), [tests/test_descriptor_catalogue.py](../../../tests/test_descriptor_catalogue.py).
