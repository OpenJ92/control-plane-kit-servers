# `test_topology_client.py`

The #371 target case loses only the final advancement response after the existing
scripted public route fixture reports completed execution. One apply must report
execution succeeded, advancement unverified and attention required, then retain
that result in the existing journal without changing its executed phase, pending
intent/idempotency, coordinates or successful request history. The fixture takes
its snapshot at the dispatched advancement boundary; it does not seed journal
state or recreate Operations acceptance. This tests-only checkpoint has not run
and earns no target-red evidence. Production and dependency pins are unchanged;
execution uses only the established repository Docker suite after its prerequisites
and gate boundary are ready.

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
