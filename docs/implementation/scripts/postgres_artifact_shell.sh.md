Source: [postgres_artifact_shell.sh](../../../scripts/postgres_artifact_shell.sh).

Explicit routes from the owning test.sh: daemon-free PostgreSQL unit tests,
source-image lifecycle, or separately authorized actual-digest qualification. All require an existing
immutable controller and new private receipt directory. Published mode passes
only the four explicit product selection variables, source/fixture mounts and
daemon socket to the existing witness. Published mode performs no controller or
product pull/build; source mode preserves its witness-owned product build.
Exit status and logs are retained; there is no retry.
Published mode allocates a random run identity with mktemp under the private
receipt directory and retains `run.id`; receipt basename is never the identity.
See [artifact procedure](../../managed-postgres-artifacts.md).

Both lifecycle modes share a shell-owned internal bootstrap network and exact-ID
controller launch/cleanup. Shell ownership uses `org.openj92.cpk.controller-run`
and names outside the witness run namespace, preserving the witness's freshness
refusal. Both carry the project label for the final residue audit. The controller
joins the witness-owned internal lifecycle network for management requests.
No default bridge or host network is selected; internal networking is not host
isolation, and the controller retains explicit daemon authority.

Traps precede resource creation. Cleanup verifies exact controller identity and
ownership, removes it, then requires the exact owned internal network to have no
endpoints before removing it. Foreign endpoints are never forcibly disconnected.
Unknown creation, cancellation or cleanup failures retain private evidence and
remain failures, without retry or discovery-based deletion. SIGKILL cleanup cannot
be promised. Fixtures are removed only after shell resource cleanup succeeds.
Source mode rejects published selection variables and preserves the existing
witness-owned build/image removal. Published mode never builds or removes its
borrowed image. Unit mode stays socket-free and network-none. Normal source CI
uses this same launch path once; it does not produce published-image evidence.
