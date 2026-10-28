Source: [test_dynamic_managed_provider_selection.py](../../../../../products/cpk_server/tests/test_dynamic_managed_provider_selection.py).

These #341 targets specify the trusted selector boundary without simulating
assignment history. A failing UoW is the only policy-store substitute: actual
ManagedRuntimeSelectionService must refuse unavailable current lookup without
constructing a Docker client or falling back to static bindings. Malformed or
revoked input is refused before lookup. The installed catalog must match its
existing capability policy exactly and cannot mix static workspace bindings.
Existing static selection/custody tests remain the separate compatibility proof.

At the test-only checkpoint the installed capability binding interface was
absent. Its initial assertion stopped each target before deeper behavior.
Positive/current grant and revocation proof belongs to actual public
management writes and real PostgreSQL owner selection in the existing witness,
not a fake store transition in these unit tests. The64 capability bound comes
from the configured installed catalog; it is never a workspace limit.

Run40592857952 passed integrity/install/collection and both
targets reached only the absent-binding assertion. All deeper target assertions
and the public management witness remained unreached. The implementation now
supplies that interface; the unchanged targets await owning green evidence.
