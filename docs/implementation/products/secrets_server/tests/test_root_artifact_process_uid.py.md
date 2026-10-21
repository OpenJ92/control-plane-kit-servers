Source: [test_root_artifact_process_uid.py](../../../../../products/secrets_server/tests/test_root_artifact_process_uid.py).

SOURCE review of #191 identified a missing selected-artifact process UID witness.
These five new-law targets preserve the accepted 18 artifact targets and exercise
the existing admission owner. They require CPK PID 1 effective UID 10001 and
Secrets PID 1 effective UID 10006, distinguishing the effective column from real,
saved and filesystem IDs. Cross-role/wrong/root IDs, absent observations, malformed
or duplicate UID rows and oversized status text fail with a fixed redacted error.

The planned observation is a bounded read of `/proc/1/status` inside the selected
running container, never `os.getuid()` in a new exec process or an environment
read. The shared verification call already runs for CPK startup and both Secrets
starts. Tests establish the parser contract, not actual-artifact acceptance.

At the test-only checkpoint the proposed callable is absent, so each method must
fail at the explicit missing-behavior assertion. Execute only via the established
hosted owning Docker `./test.sh`, after target review. No source fix accompanies
this checkpoint.
