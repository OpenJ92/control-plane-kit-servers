# Managed cloudflared owning package stage

Source: [cloudflared_managed_witness.sh](../../../scripts/cloudflared_managed_witness.sh).

Servers #284 invokes this stage unconditionally from normal test.sh after the
historical connector witness. It builds the distinct managed Dockerfile, records
its exact image ID and invokes the package controller in the existing test image.
Only that controller has the daemon socket. Image fixtures use network none,
no host ports and no credentials/configuration. The same image supplies contents,
controlled stop-profile and fatal-PID1 cases; none is positive live qualification.

Unique ownership-label absence is checked before creation. Cleanup checks each
container's label and the recorded image/tag identity before deletion; no broad
prune occurs. The controller verifies created IDs, while shell fallback covers
its run label. Trap cleanup preserves failure if removal cannot be verified.
After containers are gone, only named result files are unlinked and the results
directory must be empty. Unexpected files fail cleanup. Obsolete synthetic
control/token/request file cleanup was removed together with their producers;
only containers.json and image remain as named top-level records.

The final marker explicitly says package stage passed and live qualification
pending, after container/image/fixture cleanup. Controller package_pass covers
only its observations and container cleanup. Later PostgreSQL and final global
residue stages remain mandatory and cannot be credited from the earlier marker.

This local package-lane change awaits exact source review and owning Docker
green. Prior failures and target-red39451603339 remain recorded on #284; no
standalone stage, alternate harness or manual duplicate run is authorized.
The approved source/package versus mandatory later CPK/Cloudflare split retains
all real native acceptance laws. #284/#188 stay open, and no provider, credential,
public ingress, dependency or publication effect is introduced.
