Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/__init__.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/__init__.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This product-local facade re-exports installation values/factory, HTTP and MCP
application boundaries, development credential verification and process
composition/state types. It imports those owner modules eagerly; it is not the
lightweight root product catalogue.

There is no call here to start the server or instantiate an installation.
Effects and dependency construction belong to the named factories and process
entrypoint. Importing this facade should not be confused with decoding a Core
descriptor, and its export list does not prove every transitive import is
effect-free. Read the corresponding owner before changing public exports or
moving responsibility across this facade.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/boundary.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/composition.py), [products/cpk_server/tests/test_process_composition.py](../../../../../../products/cpk_server/tests/test_process_composition.py).
