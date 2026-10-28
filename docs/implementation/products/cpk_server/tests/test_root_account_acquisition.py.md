Source: [test_root_account_acquisition.py](../../../../../products/cpk_server/tests/test_root_account_acquisition.py).

The command's admission laws reject wrong repository, mutable reference, malformed
producer and a missing producer-job context before acquisition/output creation.
Credential canaries must not enter stdout/stderr. These tests run only through
the normal owning Docker suite; they do not create mounts, contact registries,
run Docker controllers or prove a successful publication/inspection/cleanup.
