Source: [products/cpk_server/Dockerfile.bootstrap](../../../../products/cpk_server/Dockerfile.bootstrap).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This builds an external acquisition driver on the caller-supplied CPK_IMAGE,
then overlays the checkout's CPK process source and selects bootstrap_cli.
It is not a fourth graph-visible CPK product. The base argument has no default
or validation here; the bootstrap plan/runtime must admit its actual identity.

The driver runs as root because existing archive/materialization helpers need
that access on new volumes. That image default is not permission for every
bootstrap phase. The runtime creates the later public-setup helper explicitly
under the inspected CPK UID with only plan/credential mounts and the CPK network
namespace, without the Docker socket. Dockerfile comments describe that
separate runtime boundary; this build recipe does not enforce the helper's
launch options, approve acquisition or authorize retry.

Related source and evidence: [products/cpk_server/Dockerfile](../../../../products/cpk_server/Dockerfile), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py](../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py), [bootstrap.sh](../../../../bootstrap.sh).
