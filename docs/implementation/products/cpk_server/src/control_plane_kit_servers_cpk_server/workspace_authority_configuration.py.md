# Installer workspace policy configuration

The closed `cpk-server.workspace-authority.v1` document contains installation_id,
administrators, known_identities and opaque capability IDs. Full identities use
issuer/subject_id/kind. Existing Operations values own identity uniqueness,
administrator membership and capability semantics; no store, grant, seed or
credential behavior is implemented here. Owner collection limits remain 1–1024
identities and at most64 capabilities, independently of durable workspace count.

The pure decoder rejects unknown/duplicate fields, nonfinite JSON and malformed
values. The reader follows the existing managed-health regular-file/no-follow
pattern, reads at most1 MiB+1 and closes in finally. Parent directories must be
installer-trusted. Fixed errors are raised outside exception handlers so input,
path and underlying exception context do not escape. No public artifact helper
is provided for this policy. Source work does not install or change a policy.
