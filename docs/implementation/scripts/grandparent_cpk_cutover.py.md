# Issue-specific retained CPK cutover proposal

Source/action preparation under Servers #399. Reuses the earlier cpk384/web65
replacement sequence and bootstrap_runtime's declared Docker create/inspect/start
mechanics. No general updater, bootstrap replay, CPK graph or durable store owner
is added. The sole old/candidate image, engine, instance, port and mount identities
are closed. This source is not authority to execute it.

Private environment values move only in the maintenance process's Docker API
memory, never command arguments or records. The two public saved-state reads
are checked before outage and compared after readiness. Public revision shape is
Ops701 read_services/desired_topology_drafts.detail/FocusedDetailReadModel.
The exact original stops gracefully, is renamed and disconnected before the
successor obtains its original name/semantic alias and port. Created successor
configuration/private wiring is verified by returned ID while stopped. Startup
may commit schema work before later checks fail; no automatic rollback occurs.

The supplementary North-owned maintenance receipt identifies the current CPK;
the original bootstrap inspector sees the retained original stopped by design.
Finite Docker/read frames cover ordering, pre-outage read failure, pre-start
wiring/mount refusal, ambiguous create, failed post-start checks and no replay.
They prove neither actual DNS/port handoff nor installed/private state. Owning
validation is ./test.sh --grandparent-artifact-source-tests, with no socket,
network, credential or live input. Exact future action inputs/approval and the
Docker-backed invocation remain separate from that source-only gate.
