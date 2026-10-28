Source: [test_workspace_initialization.py](../../../../../products/cpk_server/tests/test_workspace_initialization.py).

#346 targets the fixed-input initializer boundary: actual administrator mapping,
private intent and exact target/package correlation before database access,
fixed connection selection and bounded pending evidence on connection failure,
closed CLI flags, existing writer-lock refusal, and no redispatch of an unresolved
inspection even if its prior read matched. External connection/provider seams do
not recreate Operations semantics. The existing dynamic bootstrap tests continue
to require the pre-Docker full-apply guard until #347 composition.

The protected synthetic input fixture reuses #345's authored installation and
actual private admission. Target and production evidence are separate: these
new targets have not executed at their initial checkpoint. The actual database
boundary is covered by workspace_initialization_acceptance in the owning gate.

Target review distinguishes unknown credentials from a real verified known
non-administrator. The latter is present in the actual principals document and
policy known identities, but not its administrators. Both must refuse before
database access/progress and return bounded context-free errors.
