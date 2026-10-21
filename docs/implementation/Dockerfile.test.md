Source: [Dockerfile.test](../../Dockerfile.test).

The existing owning unit image installs this repository and runs its unchanged
run_all_tests.py entrypoint. Servers #301 adds the root bootstrap.sh file to the
existing root-file COPY because the commissioning targets execute that actual
shell launcher with a recording external Docker boundary. No alternate launcher,
runner, source mount, gate option or host execution is introduced.

The first full source run 39665897039 failed because the file was absent. Kepler
independently confirmed the cause before this correction. The shared launcher
test helper additionally asserts file presence, preventing a missing-file exit
from masquerading as an unsafe-parent refusal. All prior gate evidence limits
remain until the normal owning gate completes successfully.
