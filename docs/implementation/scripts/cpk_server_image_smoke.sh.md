Source: [cpk_server_image_smoke.sh](../../../scripts/cpk_server_image_smoke.sh).
Maintain with the owning smoke profiles and local synthetic effect plan.

wrapped-source requires the existing test/controller image and the new source
receiver. published-baseline explicitly retains historical inputs and checks;
there is no runtime health-disable or fallback after source admission failure.
The source image still has only its src copied and runs UID10001 on8080.

After build/PostgreSQL readiness, create one mktemp directory0700 and invoke the
owned fixture generator in the test image with no network and host UID/GID.
Public control.json0444 is mounted alone, readonly, to the fixed receiving path;
UID10001 can read this public file. Separate0600 header files remain outside CPK.
First reject source startup with otherwise complete bootstrap but no control file.
Then run actual source and use curl header-file references (never token arguments),
connect timeout1s/request timeout3s/max response65,536 bytes. Require authenticated
static/liveness success, missing authority401 on both routes and wrong-purpose401.
An in-container no-network verifier checks response identity/declaration/outcome.
Legacy HTTP/MCP/readiness/history checks still run afterward.

Each grant lasts240 seconds from generation immediately before startup; no build
latency is charged to that window. Header/response files remain private via077
umask. Remove exactly control.json, surface.headers, health.headers, surface.json,
health.json and denied.json after container cleanup; rmdir proves the directory
empty/absent. EXIT/INT/TERM failure handling repeats exact cleanup as needed and
returns failure if new file cleanup fails. No broad prune, provider mutation,
credential refresh or unrelated cleanup is added. Existing diagnostic limitations
and ownership of the normal Docker effects remain unchanged.

The missing-control rejection probe uses a separately created, run-labelled/named
container whose exact ID is retained before start and included in existing cleanup.
At most15 one-second state inspections require exited/nonzero, then at most4096
bytes from the last10 log lines prove the fixed receiving error. If missing-file
enforcement regresses into a running server, the gate fails boundedly and cleans
the exact ID; it does not block in a foreground docker run or use a generic runner.
