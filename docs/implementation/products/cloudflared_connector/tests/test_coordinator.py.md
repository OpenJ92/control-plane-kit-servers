# Coordinator new-law targets

Source: [test_coordinator.py](../../../../../products/cloudflared_connector/tests/test_coordinator.py).

All five groups are new-law targets under Servers #188, after the reviewed
configuration/health/SDK predecessor PR278. They use the frozen coordinator plan
SHA2569f517197510a53cb4af9920082bc4c1508647ae3ebec00d2f7d46a71aac7e1ec and both
reviewers' interface details. Existing managed-configuration/auth/health mapping
targets remain predecessor coverage, not duplicated coordinator state machines.

- Partial startup: invalid configuration/path/NUL before effects, no-child early
  cancellation, stop during spawn/bind, cleanup after failed spawn/bind or serving
  thread start. A never-started host must not create a blocking shutdown wait.
- Failure: native0/nonzero/signal mapping, host return/exception, failure surviving
  later child0, native nonzero on requested stop and forced124 precedence. Joined
  host completion plus native exit proves competing available observations;
  a requested signal delivered during cleanup cannot erase unexpected native0.
- Signals: TERM/INT once, expected host completion versus failure, nondefault handler restore,
  repeated signals preserving the first clock and one separate KILL.
- Deadlines/ownership: stalled host shutdown concurrent with native cleanup,
  leader exit not group absence, group observation uncertainty and unreaped child.
  Measure deadlines from the actual first handler delivery, not the fixture's
  scheduled timestamp. Observe actual supplied health and listener closure while
  native/helper cleanup is still pending, not only after run returns.
- Custody: actual Popen fixed argv/one-key environment/group/DEVNULL; owned
  non-inheritable pipe duplicate, no flag mutation, unsupported/setup/full/broken/
  partial diagnostic destinations and close failure. No output queue or thread.

The intended causal red is NotImplementedError at collected callable/helper
scaffolds, not import, fixture or Docker failure. No red has been run yet. The
owning unmodified Docker ./test.sh remains the only execution gate; push the candid
target checkpoint before that run. A returned integer is not actual process-exit
evidence. Managed-image, undrained pipe, selected Docker stop/profile, active SDK
request, native offline behavior and exact residue remain separately staged.
