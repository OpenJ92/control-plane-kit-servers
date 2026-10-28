Source: [inspect_root_accounts.sh](../../../scripts/inspect_root_accounts.sh).

Prepared #347 offline invocation, actual unpack unrun and not effect-authorized.
Its source/synthetic laws passed ac144857's normal gate. Arguments are
the reviewed existing controller image ID, exact acquired input directory,
exact directory containing the pinned umoci binary, a new private output
directory, immutable CPK reference and producer revision. Required input names
are original.json, platform.json and layout/ (tag inspected). Acquisition remains
separate and must have its own exact Skopeo provenance and enforced disk/time
bounds before any execution release. This wrapper never fetches tools or images.

The controller must already exist as an exact SHA256 ID on Linux/amd64. It runs
once with pull disabled, the nonroot invoking UID/GID, no network/socket/registry
credential mount, read-only source/input/tool mounts and root filesystem,
dropped capabilities and no-new-privileges. Unpack uses a 4 GiB noexec tmpfs;
temporary process files use a separate 16 MiB tmpfs. Memory is limited to5GiB,
processes to64 and CPUs to2. The outer wall limit is300s plus a15s termination
grace; the umoci child separately has180s. Those are proposed resource bounds,
not an authorized allocation or an assertion that every future image will fit.

Unique run name/label and cidfile identify only the owned diagnostic container.
Failure remains HOLD and retains private bounded-stage/error evidence; no blind
retry, force deletion or global cleanup follows. On success an authoritative
inventory must show the auto-removed container absent before candidate.json is
renamed account-seal.json. Removing the container discards its owned tmpfs;
borrowed images, input artifacts and unrelated resources remain. Acquisition
input cleanup is a distinct exact-path action in the execution packet.

This source is not a new package test runner or a general controller framework.
It is a diagnostic prerequisite whose projection tests use ordinary ./test.sh.
The wrapper has not performed actual account unpacking. The same-producer
acquisition candidate supplies the already-used policy image by verified ID;
it must not acquire a new controller or mistake source CI for an account seal.
