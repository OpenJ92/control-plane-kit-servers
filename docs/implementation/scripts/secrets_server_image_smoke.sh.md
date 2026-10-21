Source: [secrets_server_image_smoke.sh](../../../scripts/secrets_server_image_smoke.sh).
Maintain with the owning product recipe, fixture and image profiles.

#191 adds wrapped-artifact/build0/controller-build0 for the explicitly selected
current digest. Existing public-file factories, signed reads, provider storage and
restart checks are reused. The selected process is pinned to the admitted actual
image ID with pull disabled; both initial and restart container Image/cache and
actual installed direct_url provenance are checked through the existing controller.
Two bounded public evidence/status files join the existing private fixture cleanup.

The existing finish owner now captures every container/volume/network inventory
status, removes only its run-labelled observations, and requires fresh successful
absence inventories. Removal/inventory/residue failures aggregate without retries.
Private-file cleanup must also succeed. Final smoke PASS moves from the body to
this finish boundary and appears only for primary+cleanup success; selected ABI
PASS follows it. Input images are never deleted. This fixes false-success reporting
in all existing profiles without a new cleanup framework. Source/default CI still
does not qualify an unexecuted selected pair or any live #225 behavior.

#204 restores default wrapped-source build. Profile/build flags and historical
immutable-image syntax are validated before Docker, directories or traps.
Explicit legacy BUILD_IMAGE=0 selects published-baseline; contradictory inputs
cannot substitute another successful mode.

Original private/bootstrap/data setup, write/generate/replay/resolve/revoke and
retained-value restart assertions remain. Provider creation is separate from
start so its labelled resource exists first. Source mode generates a public
artifact and purpose-separated headers before each startup, after builds; checks
run immediately after readiness. Stable synthetic target/runtime uses fresh keys
and120-second tokens per phase. No signing key persists or denied token refreshes.
Historical mode creates no source authority or new receiving/image evidence.

One host-owned0700 root holds initial/restart directories. Generation uses the
host UID/GID and network-disabled controller; control.json is0444 and headers0600.
Provider mounts only control.json read-only at the recipe ENV path. Root check/log
controllers use read-only mounts without a daemon socket; only HTTP checks use
the provider network.

Both profiles capture all logs through a1048577-byte limiter into fixed0600
provider.log; separate0600 log.status records producer exit status. Consumer
failure, failed/missing producer status or capture exceeding1048576 bytes fails.
The helper checks old markers/exact private values and source tokens without
matching output or token argv. Capture does not create a hard Docker deadline.
HTTP has bounded accumulation and per-operation timeouts, not a total deadline.

Finish retains labelled Docker cleanup and namespace audit, then deletes exactly
two root log files and three files per known phase. Partial generation/check
failure follows the same path. Unknown files or failed removal prevent rmdir
and retain the recorded path; no recursive prune or foreign-resource cleanup.
The first full owner run passed both profiles, including initial/restart signed
source reads and original custody/retained-value checks. Source success cannot
substitute for published qualification or public grandparent acceptance.
