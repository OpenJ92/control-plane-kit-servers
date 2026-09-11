Source: [products/cpk_server/tests/test_installation_control_auth.py](../../../../../products/cpk_server/tests/test_installation_control_auth.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This suite checks the two control-auth values across installation composition
and selected real bootstrap/server adapters. It uses synthetic references,
principal credentials and temporary material files, without provider or
runtime effects.

Closed codec cases preserve the default single-operator mode and reject
unknown/extra/missing fields, raw reference strings and reuse of the setup
bearer as the principal document. Multi-mode graph assertions retain one
principal-document secret delivery and remove single-mode public fields.
Changing only the setup bearer leaves that graph unchanged; changing the
principal-document reference changes it. Selected fixture token strings are
absent from the encoded graph, not evidence of universal secret detection.

The root plan keeps both setup bearer and principal document in required
material. Its material-reader test creates the exact private index/files,
then removes the bearer entry and expects rejection. It does not perform
setup, resolve a live credential provider or prove filesystem race resistance.

A server configuration built from the composed auth environment produces real
operator and worker principals. Actual pinned Operations policy denies worker
claim authority to the operator even with the same scope, permits the worker,
rejects another workspace and denies that worker approval authority.
The test also checks one token's absence from configuration repr.

Inherited single-mode public grants are removed for multi mode; secret-shaped
public credentials and incompatible base auth deliveries are rejected.
These are composition/authentication/policy witnesses at the selected
boundaries, not full server routing, principal-document secrecy or live
bootstrap acceptance.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/installation.py), [products/cpk_server/tests/test_docker_installation.py](../../../../../products/cpk_server/tests/test_docker_installation.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/authentication.py).
