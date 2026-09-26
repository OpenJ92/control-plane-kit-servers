Source: [live_numeric_bootstrap.py](../../../../../products/cpk_server/tests/live_numeric_bootstrap.py).

The existing owning numeric bootstrap fixture exercises CPK's actual image/default
UID10001, account/HOME and protected0400 file delivery. Issue235 additionally
materializes an empty explicit source-support ConfigurationArtifact through the
real Docker SDK, verifies its digest and mounts it readonly. The same recipient
proves the file is root-owned0444, readable by UID10001 and unwritable, imports
the real CPK entrypoint and reads it through the support loader. That entrypoint
must include its real gateway/Hello codec dependencies in the standalone image.

The new volume/container remains in the existing exact-resource cleanup ledger.
No extra provider or published-image action is added. Empty support proves the
installed input path and file contract, not managed execution, policy admission
for a workload, image qualification or full181/225 readiness.
