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

Provider registration accepts the scenario's exact reference/intent set. Material
intake uses the existing authenticated HTTP-only provision route for either
workspace, after its independent provider write grant, then compares the public
request receipt. Intake owns custody and reference admission; the scenario does
not seed provider state or recreate admission. Material is not returned by the
helper or retained in its request mapping after dispatch. This remains unexecuted
scenario preparation pending composition with the selected workload documents.

Sequential authority helpers now read current revisions, submit one explicit
revoke, inspect current authority, replay the original grant command, and verify
that it does not revive permission. Ordinary and management restoration use new
explicit command identities with freshly read revisions to separate experiments.
Management revocation also checks that ordinary permissions did not change.
These are public authority observations, not proof of a denied provider effect.
The scenario still needs the actual operation and the approved G layered evidence:
exact-cohort owner tests, review of deployed composition, and real public behavior.
Independent live acquisition/request counting remains unproved. A provider-policy
refusal intentionally reaches Secrets and cannot establish zero Secrets HTTP.

The topology transition helper delegates preparation, exact-plan approval,
execution, graph advancement and bounded public status reads to `TopologyClient`.
The reviewed scenario supplies its expected destructive/non-destructive approval
kind; a different kind, incomplete execution or unverified current advancement
raises before success can be reported. It makes one plan/apply call, does not
retry an uncertain result, and does not treat a no-change plan as evidence of
workload creation/removal. Its independently read status must retain the exact
workspace, operation, plan and run coordinates. Actual desired documents and
their reviewed transition scope remain the caller's responsibility.

The isolation helper uses each ordinary credential through both HTTP and MCP,
first verifies its own current-graph access, then requires authorization refusal
for the other workspace's current graph and actual plan/run paths. This is only
foreign-workspace evidence; foreign child/cursor IDs under an authorized
workspace, grant isolation, and full-identity verifier cases remain separate.

This checkpoint is incomplete source preparation. The early G dispatch,
two-workspace workload progression, actual denied-use checks,
restart/upgrade evidence, and verified cleanup are not yet composed. The
launcher-only fixture must not run as G acceptance. Its normal context exit
permits fixture disposal, so the final scenario must raise for every failed,
incomplete or uncertain outcome and return normally only after verifying all
applicable public results and approved desired-empty cleanup.

The fixture imports the reporting owner as
`scripts.cpk_server_source_live_report`; integrated G reporting must use that
same module identity so `SourceLiveRunFailed.primary_code` survives finalization.
No executable validation or live acceptance is claimed by this checkpoint.
