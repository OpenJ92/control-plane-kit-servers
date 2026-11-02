# Managed cloudflared owning package stage

Source: [cloudflared_managed_witness.sh](../../../scripts/cloudflared_managed_witness.sh).

Servers #284 invokes this stage unconditionally from normal test.sh after the
historical connector witness. It builds the distinct managed Dockerfile, records
its exact image ID and invokes the package controller in the existing test image.
Only that controller has the daemon socket. Image fixtures use network none,
no host ports and no credentials/configuration. The same image supplies contents,
controlled stop-profile and fatal-PID1 cases; none is positive live qualification.

Unique ownership-label absence is checked before creation. Cleanup checks each
preflight listing's command status before treating empty output as absence.
Failed preflight observations stop before build/run or volume acquisition.
Cleanup checks each
container's label and the recorded image/tag identity before deletion; no broad
prune occurs. The controller verifies created IDs, while shell fallback covers
its run label. Trap cleanup preserves failure if removal cannot be verified.
The #225 result channel uses one fresh run-owned local volume shared by the
controller and contents helper, with no initial image-content copy. Host records
remain separate. After controller exit, volume cleanup requires recorded
association, an empty-volume marker and zero references. Rejected result files
retain the volume and make cleanup incomplete. Only fixed host records are then
removed; unexpected host files make directory removal fail. Normal and contents
paths each perform one EXIT cleanup attempt, including on failure; no cleanup
retry follows a failed explicit cleanup.

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

## Selected candidate release mode (#308)

The owning `test.sh --managed-connector-candidate` entry delegates here before broad gate setup. Explicit arguments route to the product release policy through `cloudflared_release_shell.sh`, reusing the packaged controller unchanged. Unlike default package mode, the supplied exact image is borrowed and retained; evidence is written to a new caller-selected directory. No implicit image build/pull occurs. A controller failure cannot authorize publication, and a missing/partial receipt never proves success. The original no-argument build/owned cleanup stage is unchanged.
#225's explicit contents-only route is selected by the owning release shell,
after borrowed controller receipt/image admission. It reuses this script's one
current-source managed fixture build, controller mounts and strict helper reader.
The controller receives `contents-controller`; default invocation remains full.
No profile/fatal fixture or Engine admission is performed in observation mode.

Observation receipts retain run and created fixture-image identity, and a closed
result separately reports invocation success/failure and verified/incomplete
cleanup. The common EXIT handler cleans only exact owned resources and writes
the result after cleanup; success is never package qualification. An unknown
tag left by a build before image-ID recording is preserved and cleanup refuses.
Unexpected remaining files make rmdir fail rather than yielding a false cleanup
claim. Borrowed controller images and the retained evidence directory are not
deleted. Build logs stay private in the owning route's observation.log.
