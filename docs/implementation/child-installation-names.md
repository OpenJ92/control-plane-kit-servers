# Retained child naming intent

Source: [client/child_names.py](../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/child_names.py).
Maintain this companion with the naming implementation.

`create_child_names(binding)` explicitly creates a new installation's local
naming intent or returns its identical acknowledged record.
`reopen_child_names(binding)` requires the existing complete record.
Both return an immutable assignment with a random UUID label and deterministic
API, website and management hostnames. They perform local filesystem operations.

The authoritative location for this OS account is
`~/.local/state/cpk/child-installations/<key>.json`. The key covers the canonical
parent API origin, parent installation, parent deployment workspace and child
installation. Zone, role authority references and explicit ingress lifecycles
are checked inside that record. Image versions, client operation IDs, profile
names and working directories have no effect on the names.

The parent target is a canonical origin. HTTPS uses the existing frontend
origin validator; explicit default ports and path prefixes are refused.
The client profile's deliberate loopback HTTP policy is retained with the same
origin-only restriction and a single default-port spelling.

This is local intent. Before explicit creation the caller must establish that
the child is new. Missing local state cannot establish global absence. Preserve
the exact record when moving the workflow to another account or host. Reopening
missing or interrupted state requires investigation and never allocates a new
label. Changing an existing binding requires a separately designed transition.

An exclusive pending file contains the candidate assignment. Publication syncs
its bytes, links it to the final name without replacement, syncs the directory
and verifies the committed assignment. Only its creator removes the pending
file, after checking the recorded inode, and syncs that removal before returning.
Any surviving pending file takes precedence over final state. Contending callers
receive the committed matching assignment or a refusal. Publication uncertainty
preserves the files for investigation. No caller overwrites or repairs them.
An existing-record return independently syncs pending removal and rechecks both
absence and the assignment. It cannot rely on an overlapping writer's sync.

The record carries planned authority references. Exact-host authority
registrations can be created only after their names are known. A separately
reviewed binding step must verify and pin the real registrations to this exact
assignment before submission. Normal execution admission still checks current
authority. Names confer no permission, reserve no provider resource and make no
claim about website reachability or health. Explicit ingress lifecycle values
remain part of the proposed deployment contract.

The naming functions never submit a plan. A hostname-occupied outcome from a
later provider operation leaves this assignment in place. The maintained client
continues to own operation journals and ambiguous plan recovery.

`test_child_names.py` covers persistence, binding conflicts, two children,
concurrent creators/readers, interrupted publication and directory durability.
Executable evidence uses the repository's unchanged Docker-backed `./test.sh`.
Naming acceptance is independent of the later authority binding, managed child
graph, credential preparation and live installation acceptance.
