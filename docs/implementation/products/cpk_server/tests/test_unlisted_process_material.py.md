Source: [test_unlisted_process_material.py](../../../../../products/cpk_server/tests/test_unlisted_process_material.py).

S1 #249 boundary targets call the existing process compute port with public Core
request/material/selection values. The tiny process double records the installed
state visible during an effect and supplies independent observed incarnations.
It proves ordering, correlation, and failure reporting, not physical installation.
The prior process epoch intentionally differs from the compute port's stale
pre-restart observation. Pre-stop failure must fail; post-stop failure must remain
uncertain. Neither may publish desired material, selected refs, or a success receipt.
The joined owning smoke provides the separate actual file/process/business proof.

These targets precede implementation. The normal Docker-backed owning gate is
the only executable validation; no collection/import/setup failure earns causal
missing-behavior credit. No provider resources or credentials are used here.

The released diagnostic addition tests exact command/result/error identity and
preservation of the original failure when its observer fails. A separate bound
checks at most four diagnostic records and absence of raw exception values.
These cases add no successful replacement or recovery claim.
