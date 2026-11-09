Source: scripts/http_sample_source_assembly.sh.

The narrow managed-startup phase selects five startup tests and the existing
actual registration regression, exact immutable source exports plus this actual
checkout mounted before cached code, no network/socket/DB/build. Existing
managed-composition also names startup tests. The grandparent artifact successor
adds its standard-library local OCI integrity regressions to the same owning
managed-startup selection. They exercise synthetic bounded tar data only, not a
Docker base fetch or build. The owning fake-CLI build-termination regression also
checks that a nonzero buildx child retains unconfirmed scratch without retry.
Source-gate receipts remain revision-specific.

Only managed-startup uses `/tmp:exec` so finite fake CLIs can execute; other phases
retain their previous tmpfs mode. The fake-build test supplies its own disk-space
observation rather than depending on the source container's tmpfs capacity.
