Source: [Dockerfile.test](../../Dockerfile.test).

#191 target preparation installs real `jq` in this test image because its shell
boundary test executes the existing workflow's actual manifest validation before
optional artifact admission. Replacing jq or copying that validation would mask
the owning path. This is test apparatus only: no product image, runtime dependency,
workflow or gate command changes. It is unvalidated until the normal hosted gate.
The Debian package resolution follows the existing mutable test base; it is not
claimed as a new reproducible production dependency lock.

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
