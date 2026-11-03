#371 adds a typed owner failure through the real authenticated FastAPI host, PublicHttpTransport, TopologyClient.apply and a reloaded real journal. Earlier commands use the existing scripted composition fixture; no Operations acceptance state machine is recreated. It checks unchanged pending/history/coordinates/phase, unresolved read-only status retention, rejection of tampered journal evidence on read/write, human/JSON rendering and existing successful replay supersession. A bounded negative transport cohort proves body cap/closure, safe-status retention, malformed/duplicate/extra/substituted evidence rejection, authorization preservation and no raw error context. An injected transport case proves independent workflow rebinding. These cases and the earlier reporting/save-failure cases await the one consolidated normal Docker gate.

# `test_topology_client.py`

The #371 target case loses only the final advancement response after the existing
scripted public route fixture reports completed execution. One apply must report
execution succeeded, advancement unverified and attention required, then retain
that result in the existing journal without changing its executed phase, pending
intent/idempotency, coordinates or successful request history. The fixture takes
its snapshot at the dispatched advancement boundary; it does not seed journal
state or recreate Operations acceptance. Tests-only checkpoint
`c21cd8fdf8e62e096ef3566f1687925a2ad5bd27` ran once through ordinary `./test.sh`:
the CPK group ran 737 tests in 117.366 seconds with this target's expected
`not-started` versus `succeeded` assertion as its only failure. Whole gate exit
was 1; preceding groups, build, integrity and initial compilation passed. Later
product groups, clean import and daemon smoke stages were not reached. Production
and dependency pins remain unchanged. This establishes the reporting defect,
not a diagnosis of the server refusal or full acceptance; see
[the terminal record](https://github.com/OpenJ92/control-plane-kit-servers/issues/371#issuecomment-6595189545).

The implementation checkpoint extends the same fixture to an invalid advancement
response and an authorization refusal, preserving the latter's original exception
and journal. Save-failure cases inject failure before writing and at the real
directory fsync after replacement. Both require one save attempt, one advancement
dispatch and a bounded JournalError; pending intent/history/coordinates remain
unchanged even though the stored last_result can differ. These additional cases
have not run; the consolidated ordinary green gate remains pending.

The completed-operation regressions use the real client and the existing
`ScriptedTransport` public-route fixture. They first plan and apply to genuine
convergence, then replay through the same or reconstructed client, requiring
fresh public evidence, exact operation/plan/run identities and zero commands.

Independent graph drift, projection drift and unavailable current reads are
armed only after convergence and tested through both status and apply. They
retain freshly verified execution success while requiring unverified advancement.
Unavailable workspace, plan and approval reads before run evidence require both
observations to remain unverified, again with no commands. Tests do not rewrite
the journal to manufacture convergence. Existing pending/lost-response tests
remain in the normal owning suite.
