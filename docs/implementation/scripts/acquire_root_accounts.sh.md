Source: [acquire_root_accounts.sh](../../../scripts/acquire_root_accounts.sh).

Opt-in #347 diagnostic entrypoint. Its default path is called after a successful
CPK publication in the same hosted job, with its actual immutable reference and
producer source. It never publishes. Source/ref/job admission, required installed
tools and the exact borrowed policy image are checked before target acquisition.
The default path still stops on missing/drifted cache and never pulls/builds/loads
a controller. The separately released retained-publication mode is described below.
The immutable Python policy reference is the one selected by the producer's
existing override. This does not cap that producer's earlier image/build storage.

The default same-producer job has packages-write authority. Acquisition performs registry reads
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
and input metadata. No credentials or tool directory is mounted.
Only the exact reviewed projection script is bound as source; the checkout and
its .git directory are never mounted. Skopeo copies
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
Docker, mount and loop queries must succeed before their output is interpreted.
After unmount, a successful complete explicit-field mount inventory must show
the exact target absent; findmnt exit 1 is not absence evidence. A failed empty
query stops before candidate promotion or backing-file removal.
The public outcome always distinguishes known publication success from inspection
HOLD/candidate. Only allowlisted status/provenance and a successful candidate are
uploaded; raw errors, auth, manifests/layers and account files are excluded. An
inspection failure cannot undo or authorize replay of publication. Actual effects
remain separately released. The first source94 attempt published CPK but failed
at offline-inspection; successful unpack, final container absence and acquisition
cleanup were not established. Secrets remained undispatched.

The diagnostic correction preserves a closed failure classification from the
offline wrapper in the existing public status.json stage field. Reserved projection
codes become fixed offline input/layout/tool/unpack/account/serialization labels;
the wrapper accepts them only with a matching complete bounded marker. Outer
timeout, killed-or-timeout, outer execution failure and unknown controller failure
remain distinct; other wrapper failures use offline-wrapper-failure. These labels
are observations of the failed boundary, not inferred causes or cleanup evidence.
The schema and all candidate promotion conditions remain unchanged. Sourceable
inspection/status functions let the owning Docker suite test propagation using
process doubles without entering acquisition or performing provider effects.

`--retained DIAGNOSTIC_REVISION REFERENCE PRODUCER_REVISION OUTPUT` admits only
the recorded337c8cf manifest produced at94ecb34 in publication run40756067917.
The diagnostic revision must match the clean checkout and GitHub workflow source;
the mode requires the reviewed `inspect-retained-cpk` job in the registered
`publish-product-image` workflow, with retained inspection selected and same-job
inspection disabled. Selecting both stops in preparation. That job's explicit
permission declaration owns contents-read/packages-read authority; the
script does not infer token scope from an environment string. The existing
same-job mode still requires diagnostic and producer revisions to be identical.
The producer revision continues to govern image configuration verification.

The existing fresh output directory is created once. Bounded preparation HOLD
and minimal provenance are recorded before clean-source/prerequisite admission;
selected identities are not marked admitted until the checks succeed. Thus an
ordinary dirty-source or missing-tool stop cannot imply inspection or cleanup.
Invalid invocation/context, missing jq, or failure to create the fresh output
still stops without fabricating an artifact. Once admission passes, actual runner
and Skopeo provenance are recorded before the new controller acquisition phase.
Status/provenance retain producer and diagnostic revisions, current run/attempt,
and the historical publication run separately. This job asserts prior publication
from that fixed reviewed receipt; it does not publish or relabel the image.

Retained mode makes one explicit pull of the fixed public Python reference for
Linux/amd64, with a300-second CLI deadline and15-second TERM-to-KILL grace. The
controller ID/platform/repository digest are observed afterward; all inspection
containers still run by that verified ID with pull disabled. Default mode skips
this pull entirely. Failure/timeout stays controller-acquisition HOLD and does
not enter inspection or cleanup. A CLI timeout does not prove the Docker daemon
stopped downloading/extracting. There is no re-pull, fallback or prune.

North accepted this fixed controller pull in the fresh hosted runner's disposable
Docker storage as separately scoped exposure, **without an enforced image-store
quota**. Provenance records its hard limit as null. The3GiB acquisition filesystem
and4GiB unpack tmpfs bound their respective phases only; they are not a total job
budget. Source/design acceptance is not permission to execute the new workflow.

The retained-mode daemon platform observation must exit successfully before its
stdout is allowlisted. Matching platform text from a failed `docker info` call
does not admit a pull. Raw observation errors remain in the private attempt
directory; the public result stays preparation HOLD with no effect/cleanup credit.
