Source: [src/control_plane_kit_servers/__init__.py](../../../../src/control_plane_kit_servers/__init__.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

The shared root exports the version and load_catalogue entrance. It loads catalogue code but does not start a server or import product application modules. load_catalogue reads publication metadata; decoded Core product values use a separate owner function rather than a hidden root-import effect.

Keep the deliberately small facade aligned with the metadata/import tests. Convenience exports of process owners would change the cold-import contract and require reviewing their effects.

Related source and evidence: [src/control_plane_kit_servers/catalogue.py](../../../../src/control_plane_kit_servers/catalogue.py), [tests/test_package_metadata.py](../../../../tests/test_package_metadata.py).
