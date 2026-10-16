Source: [docker_image_update_capacity.py](../../../../../products/cpk_server/tests/docker_image_update_capacity.py).

Temporary #1993 diagnostic observes the actual accepted Operations owner's pure
publication forecast during the unchanged #252 Docker scenario. It calls the
original `_publication_budgets` once and returns that exact tuple. `_preflight`
and its refusal remain unchanged. The accepted owner tests already establish
that this forecast performs no SQL and does not change accounting; no second
forecast, owner-state reconstruction or additional evidence read is introduced.

At most eight records expose fixed numeric prior/snapshot/future/publication and
combined settled/peak footprints plus the owner's closed capacity decision.
Each record is limited to 16 KiB; integers are nonnegative signed-64-bit values.
The phase is pre-id or bound. No identifiers, graph/history contents, SQL,
credentials or secret material are read for output. Output errors cannot replace
the original owner's return or refusal; the method patch always restores.

Socket-free tests prove tuple/exception identity, exact once invocation, numeric
schema/count bounds, canary exclusion, untouched preflight, restoration and
preservation of its actual capacity refusal when printing fails. These are
diagnostic contracts, not acceptance-state or capacity-correctness simulations.
The normal hosted owning gate provides the one released real-route measurement.
Remove this temporary observer once diagnosis and the owner regression are
captured. A measured excess does not authorize a cap increase or production fix.
