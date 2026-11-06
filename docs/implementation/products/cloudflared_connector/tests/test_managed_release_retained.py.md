# Retained qualification boundary tests

These new-law tests use synthetic executor/image/receipt values and command
results. They protect executor refusal, exact reference-to-local-ID binding,
private-field exclusion, primary failure preservation, intent-before-pull,
stop-before-acquisition on daemon drift, existing owner invocation, and complete
success evidence. They do not reproduce Docker stop/cleanup semantics or earn
image qualification. The existing managed release test route collects this file.

Workflow tests inspect the actual parsed job selectors/default/read permissions
and execute its small conflicting-input admission snippet with synthetic values
inside the owning test controller. No generic workflow interpreter or live
dispatch is used. Route-red evidence collected 61 tests: 60 passed and the new
route test failed on the missing retained_managed_connector input before the
tests.yml adaptation.

Checkpoint 42623b4 collected 56 tests: 51 existing tests passed; five new tests
errored at explicit lookup of the not-yet-created retained qualification file.
This establishes missing-entrypoint evidence, not a behavioral execution pass.
The implementation and additional review-driven tests require a subsequent
green run through the same maintained controller route.
