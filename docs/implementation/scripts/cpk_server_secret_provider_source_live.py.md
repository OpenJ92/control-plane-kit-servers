# Public enrollment scenario integration

The G enrollment helpers select HTTP or MCP using the existing public route
catalogue and independently staged client profiles. They create workspaces,
grant finite scopes to distinct operator/approver/worker identities, and register
runtime authority through public CPK commands. Management assignment is a
separate explicit administrator action. Provider policy uses its independent
administrator profile, the observed provider revision, one command submission,
and a read of the exact resulting grant. A failed or ambiguous result stops;
these helpers do not retry or reconcile by redispatching mutations.

The maintained `TopologyClient` remains the topology workflow owner. These
helpers do not seed post-start database state, edit process configuration, or
use legacy `HostedWorkflow` bootstrap and network-repair routines.

This checkpoint is incomplete source preparation. The early G dispatch,
two-workspace workload progression, sequential revocation and replay checks,
restart/upgrade evidence, and verified cleanup are not yet composed. The
launcher-only fixture must not run as G acceptance. Its normal context exit
permits fixture disposal, so the final scenario must raise for every failed,
incomplete or uncertain outcome and return normally only after verifying all
applicable public results and approved desired-empty cleanup.

The fixture imports the reporting owner as
`scripts.cpk_server_source_live_report`; integrated G reporting must use that
same module identity so `SourceLiveRunFailed.primary_code` survives finalization.
No executable validation or live acceptance is claimed by this checkpoint.
