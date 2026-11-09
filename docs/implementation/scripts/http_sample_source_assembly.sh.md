Source: scripts/http_sample_source_assembly.sh.

The separate material-preparation phase exports the same exact sources and names
only root_material_preparation_tests; no network/socket/database/build. It is
source validation, not actual protected preparation. Evidence pending.

The narrow managed-startup phase selects five startup tests and the existing
actual registration regression, exact immutable source exports plus this actual
checkout mounted before cached code, no network/socket/DB/build. Existing
managed-composition also names startup tests. The grandparent artifact successor
adds its standard-library local OCI integrity regressions to the same owning
managed-startup selection. They exercise synthetic bounded tar data only, not a
Docker base fetch or build. The owning fake-CLI build-termination regression also
checks that a nonzero buildx child retains unconfirmed scratch without retry.
Source-gate receipts remain revision-specific.

Managed-startup, material-preparation and bootstrap-driver use `/tmp:exec` so
finite fake CLIs can execute; parent-website retains its previous tmpfs mode.
The fake-build test supplies its own disk-space
observation rather than depending on the source container's tmpfs capacity.

The bootstrap-driver phase adds exact Secrets57 exports, default/optional material
policy, website, startup, OCI and installed-import prerequisites before building.
Its public template argument is mounted read-only for the additive normal CLI
projection test. It allocates no application network, database or provider.
