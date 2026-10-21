Source: [bootstrap.sh](../../bootstrap.sh).

#301 adds commission-plan and commission-prepare to the existing launcher;
ordinary plan/apply/inspect cases are unchanged. The existing immutable local
image-ID check still runs first. Commissioning has no Docker socket, network or
material mount and explicitly uses the invoking operator UID/GID, drops
capabilities and enables no-new-privileges with a read-only container root.

Preparation receives an explicit absolute host state path. Each ancestor is
inspected without resolving symlinks; root or operator ownership and absence of
group/other write access are required. Missing components are created individually
at 0700. Existing components are never chmodded. The leaf must have the exact
operator UID/GID and mode 0700. GNU/BSD stat formats support the current Linux
test and macOS operator launch paths; preparation itself executes in the driver.

Only the exact plan file (read-only) and selected commissioning leaf are mounted.
The host path is passed as --host-state for equality against saved intent; the
container path is fixed /commissioning. Never pass the common installation root
as normal bootstrap material. This is not a distributed lock or defense against
an administrator or a malicious process with the operator's same custody powers.

The owning test executes this actual shell with a recording Docker CLI boundary;
real mapped CLI and actual driver imports/factories are separate owning checks.
No new validation runner, provider deployment or production authorization is
introduced by these commands.
