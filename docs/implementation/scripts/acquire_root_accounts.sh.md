Source: [acquire_root_accounts.sh](../../../scripts/acquire_root_accounts.sh).

Opt-in #347 diagnostic entrypoint, source candidate only. It is called after a
successful CPK publication in the same hosted job, with its actual immutable
reference and producer source. It never publishes. Source/ref/job admission,
required installed tools and the exact borrowed policy image are checked before
acquisition. Missing or drifted cache stops; no controller pull/build/load exists.
The immutable Python policy reference is the one selected by the producer's
existing override. This does not cap that producer's earlier image/build storage.

The same job has packages-write authority. Acquisition performs registry reads
using its own temporary 0600 auth file; no per-step token downscoping is claimed.
The file is removed before offline execution and never mounted into any controller.
Failure cleanup removes only that exact private auth file when present. Other
ambiguous acquisition/container/mount state is retained as HOLD, not repaired,
retried, forcibly removed or rolled back. The hosted runner's later disposal is
not claimed as observed cleanup.

A new private 3 GiB fixed backing file and exact loop/ext4 mount bound the total
input, Skopeo temporary files, tool download and acquisition diagnostics. Device,
backing and mount identity are checked. The filesystem permits execution of the
pinned umoci tool; untrusted rootfs is unpacked only on the existing noexec tmpfs.
A process-group timeout bounds the entire acquisition worker to 600 seconds plus
15 seconds termination grace. Required Skopeo version is 1.13.3; actual runner,
package and binary hash provenance is recorded. Missing/different tools stop;
there is no installer/fallback. umoci v0.6.0's exact 7,946,424-byte asset and SHA
are verified before use.

Original/platform manifests are captured with a 1 MiB bound and producer exit
checks. Two small socket-free, network-free invocations of the borrowed controller
reuse the existing strict projection owner to select one exact Linux/amd64 manifest
and admit closed config/layer descriptors and the 2 GiB compressed sum BEFORE blob
copy. Each uses an exact name/cidfile, 256 MiB memory, one CPU, 32 PIDs, 16 MiB tmpfs
and a 30-second timeout, then verifies container absence. They mount only source
and input metadata. No credentials or tool directory is mounted. Skopeo copies
that exact selected digest to one OCI layout with retries disabled; the existing
offline owner then rechecks all actual config/layer bytes and normalization.

After successful acquisition the input mount becomes read-only, the borrowed
controller ID is checked again, and inspect_root_accounts.sh owns the bounded
unpack/projection. Its 4 GiB tmpfs, 5 GiB memory and 180/300-second child/controller
limits are unchanged. The data quota and unpack tmpfs are separate limits, not a
quota on the whole publication job or aggregate resident memory.

A candidate seal is promoted to the public directory only after actual inspection,
exact container absence, matching acquisition mount/device/backing, normal unmount,
exact loop detach and backing-file removal. No force/lazy unmount or broad prune.
The public outcome always distinguishes known publication success from inspection
HOLD/candidate. Only allowlisted status/provenance and a successful candidate are
uploaded; raw errors, auth, manifests/layers and account files are excluded. An
inspection failure cannot undo or authorize replay of publication. Actual effects
and independent seal acceptance remain separately released and unexecuted.
