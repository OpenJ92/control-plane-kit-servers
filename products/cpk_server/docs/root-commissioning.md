# Offline first-root read trust

Current CPK and Secrets receivers need explicit public surface-read and
health-read trust before startup. Commissioning prepares those two public
families and stable receiver IDs without inventing a parent control plane.
Both private signing keys stay with the offline operator. This does not grant
graph execution, create API/provider credentials or establish outgoing service
signers.

Use a separately qualified immutable bootstrap driver image. The existing
driver's source must include the selected Secrets dependency and product source;
historical images cannot be assumed to contain this command. The source test
witness is not published-image qualification.

The closed intent contains schema `cpk.root-commissioning.intent.v1`, explicit
installation/workspace IDs, profile `operator-offline-read-trust`, and custody
`host_directory`, numeric `uid`, numeric `gid`. For example, after choosing the
actual operator identity and private absolute path:

```json
{
  "schema": "cpk.root-commissioning.intent.v1",
  "installation_id": "example-root",
  "workspace_id": "example-root",
  "profile": "operator-offline-read-trust",
  "custody": {
    "host_directory": "/Users/example/.local/state/cpk/bootstrap/example-root/commissioning",
    "uid": 501,
    "gid": 20
  }
}
```

These are example coordinates, not authority to create them. The operator reviews
the exact image, intent, digest, private destination and permitted own-key reuse
before preparation. The launch commands are:

```sh
sh bootstrap.sh commission-plan "$DRIVER" intent.json > plan.json
sh bootstrap.sh commission-prepare "$DRIVER" plan.json "$DIGEST" "$COMMISSIONING"
```

`DRIVER` is an existing local immutable `sha256:...` image ID. `DIGEST` is the
reviewed plan's digest; `COMMISSIONING` exactly matches the intent host path.
The launcher uses the invoking UID/GID and checks private ancestry. It creates
missing directories at 0700, never changes existing directory permissions, and
mounts only the plan plus the private leaf with no network or Docker socket.
The command prints only the public artifact/identity/fingerprint result.

Keep commissioning separate from the normal bootstrap `material` and acquisition
state directories. Never mount the commissioning directory or common parent into
CPK, Secrets or the website. Normal bootstrap receives only the returned public
configuration artifacts. Those artifacts still need exact source/image and
installation validation when wired into the root.

Custody has fixed files: lock, intent.json, receivers.json, surface-read.pem,
health-read.pem, public.json and complete.json. PEM files are 0400; other files
are 0600. Intent is durable before identities; identities are durable before
keys. Completion appears only after persisted own-key/public verification.
The multi-file process is not transactional. Any partial, conflicting or unsafe
state holds and preserves evidence. Do not delete it to retry. There is no
automatic recovery, rekey, cleanup or adoption command.

An exact completed repeat verifies its own saved keys, public output and intent,
then returns the same public result without rewriting files. Changing image,
scope, profile, destination or identity is not a retry. Locking applies only to
the same directory. Installation into services and live operational acceptance
are separate actions.
