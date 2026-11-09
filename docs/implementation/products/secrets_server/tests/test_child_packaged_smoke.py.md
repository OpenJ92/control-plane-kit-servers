Source: [test_child_packaged_smoke.py](../../../../../products/secrets_server/tests/test_child_packaged_smoke.py).
Maintain with the focused Secrets selector and exact cleanup owner.

Finite fake CLI responses prove existing receipts are untouched, collisions and
failed inventories cannot build/clean, a same-run volume from another owner
reservation cannot bootstrap or be deleted, and unexpected same-label objects
are refused rather than removed. These exercise the real owning shell/functions
inside the Docker tests without a daemon socket. They do not recreate native
provider storage or Core/Operations semantics.
