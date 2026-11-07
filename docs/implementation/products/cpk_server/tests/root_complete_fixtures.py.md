Source: [root_complete_fixtures.py](../../../../../products/cpk_server/tests/root_complete_fixtures.py).

The #302 fixture uses accepted offline commissioning in temporary Docker test
custody, retains only public artifacts, and derives actual CPK/Secrets source
contracts with their owning factories. Whitespace and a distinct valid source
digest make byte preservation observable. Synthetic website image coordinates
do not qualify images or execute provider actions. No production material is
read. The helper only supplies inputs, not a replacement acquisition lifecycle.

An optional caller-owned `commissioning_directory` now retains its matching
synthetic private inputs until the outer isolated fixture ends. Default calls
still allocate and remove their own temporary directory and return only public
artifacts. `managed_input` and the installation-management fixture pass through
this explicit test-only lifetime. The source-assembly signing law compares the
held keys to the actual installed CPK/Secrets control verifiers, then verifies
owned directory removal. This does not authorize, generate or retain live keys,
and does not stand in for normal runtime key registration/activation or grants.
