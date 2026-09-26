Source: [managed_health_support.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/managed_health_support.py).

This module owns explicit process source-support policy, not image qualification
or API product registration. The only wire profile is
`cpk-managed-health-source-support.v1`, with exactly `profile` and `products`.
Each product entry has exactly `role` and an inline canonical `document` object.
Roles are `cpk-workload`, `hello-workload`, `gateway`, and
`cloudflared-native-reader-v1`. Maximum input is1MiB and16 entries. Unknown
fields/roles, duplicate/conflicting product identities, more than one native
entry, malformed documents and missing exact receiver slots refuse.

ManagedHealthProduct and ManagedHealthSupport are frozen values with redacted
repr. Canonical documents are revalidated even for direct construction. Known
product roles bind the actual owned codecs through the existing receiver factory;
gateway contributes transit and self-health bindings. A native entry retains an
exact document for the subsequent observer composition; this parser does not
inspect its image/program or assert native capability.

The startup reader accepts absence as empty unsupported policy. A supplied path
must be absolute and bounded. It opens with no-follow/nonblocking/close-on-exec,
then checks the opened regular file, root/current owner, exact0444 public artifact
mode and size before a bounded read. The descriptor closes on every path. Final
symlinks are refused; operator-controlled parent directories and readonly mounts
remain explicit assumptions. The real existing ConfigurationArtifact materializer
creates root-owned0444 files readable by the receiving UID10001.

One successful read becomes an immutable startup snapshot. API registration,
later file edits and signing-authority reload cannot alter it. Changing policy
requires an explicitly reviewed deployment/restart. Invalid present files fail
with fixed detached ManagedHealthSupportError; no candidate bytes/path appear in
the public error. No credentials, provider effects, clocks or stores are used.

Example empty source policy (supports no managed products):
```json
{"profile":"cpk-managed-health-source-support.v1","products":[]}
```
To admit reviewed source inputs, put their exact descriptor objects in the fixed
role entries and deliver this file as a READ_ONLY ConfigurationArtifact with
`CPK_MANAGED_HEALTH_SUPPORT_FILE` pointing to its target path. The selected parent
deployment must expose/approve that policy installation. A syntactically valid
file is not independent evidence that image bytes implement these profiles.
