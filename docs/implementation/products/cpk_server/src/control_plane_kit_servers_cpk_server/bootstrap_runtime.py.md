Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_runtime.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This is the external root-acquisition effect owner, outside the Operations
activity executor. It reads admitted local material, calls Docker and runs
authenticated public setup. An existing receipt wins before material reads;
inside a nonblocking advisory state lock, receipt or partial-receipt presence
holds rather than redispatching. Successful or uncertain prior acquisition is
not automatically adopted, resumed, deleted or compensated.

Material admission requires the exact reference set (including optional pull
credentials), a private bounded JSON index and simple sibling filenames.
private_read rejects symbolic links seen in its ancestor walk, final links,
nonregular/empty/oversized files and group/other permissions. It does not check
owner UID or eliminate ancestor/check-open races. The private state/lock path
also does not establish universal filesystem race safety.

Delivery resolution uses explicit local values and the actual pinned
Interpreters adapters. Preflight compares daemon identity when supplied,
requires the exact driver with root helper ownership, checks named-resource
conflicts, and inspects or pulls product images by canonical references.
Protected-file recipients alone require numeric image ownership; provider
identity is checked against selected image environment plus planned settings.
There is no registry attestation or current-process identity witness merely
from these image inspections.

A private receipt adds a fresh acquisition label and records pending before
each wrapped effect, then IDs/selected observations before clearing pending.
Exclusive receipt.new, file fsync, replace and directory fsync provide local
persistence, not a transaction with Docker. Publication can precede a later
persistence error; partial files or effects without returned IDs require
investigation. No receipt is not proof that no effect occurred.

Acquisition creates the named network, data and secret volumes and exact-image
containers. Secret-file materialization is delegated to SDK helpers, checked
for regular file/UID/0400/content digest, and mounted through read-only subpaths.
CPK alone gets its declared Docker socket/group and loopback port binding.
Container image and secret-mount inspection precedes start. Logging is bounded;
general application-container capability/read-only restrictions are not added
by this function. SDK helper lifecycle remains its own effect boundary.

Postgres readiness uses pg_isready, not the declared authenticated SQL check.
HTTP checks use SDK probes and their policy bounds. A setup helper then shares
CPK's network as the CPK file-recipient UID, with two protected staging volumes,
all capabilities dropped and no Docker socket mount. It waits up to 240 seconds
and attempts progress recovery even on wait failure. Timeouts do not cancel or
prove completion of an external effect.

Progress recovery verifies daemon/helper/image/labels and a bounded exact
archive entry, then checks plan/workspace/route order and selected coordinates.
Completed setup permits helper removal and identity/label-checked removal of
the two staging volumes; volume disappearance is read back, while helper
removal is recorded from the call result. Other resources/material volumes
remain retained by the acquisition. Failure retains evidence and does not run
broad cleanup.

Inspect does not rewrite the private receipt. Pending state can return a hold
without Docker, or read progress from the retained exact helper. Complete state
checks resource labels and container running status; it does not recheck
authenticated readiness, image/mount identity or the external endpoint.
Receipt loading checks schema rather than a complete closed semantic shape:
private custody is not universal content sanitization. Returned local-ready
and resources-running results preserve external/readiness uncertainty.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py), [bootstrap.sh](../../../../../../bootstrap.sh), [products/cpk_server/tests/test_root_bootstrap.py](../../../../../../products/cpk_server/tests/test_root_bootstrap.py), [products/cpk_server/tests/test_root_bootstrap_diagnostics.py](../../../../../../products/cpk_server/tests/test_root_bootstrap_diagnostics.py), [products/cpk_server/tests/test_root_file_recipient.py](../../../../../../products/cpk_server/tests/test_root_file_recipient.py), [products/cpk_server/tests/test_root_image_reference.py](../../../../../../products/cpk_server/tests/test_root_image_reference.py), [pyproject.toml](../../../../../../pyproject.toml).
