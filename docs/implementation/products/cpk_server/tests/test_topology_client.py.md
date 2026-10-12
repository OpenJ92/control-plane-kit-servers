# `test_topology_client.py`

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
