Source: [test_docker_harness.py](../../../tests/test_docker_harness.py).

The witness preflight cases run its actual shell function with a deterministic
CLI double inside the owning Docker test suite. Linux/default and Desktop/named
contexts retain the observed daemon identity; remote or missing endpoints,
endpoint/TLS overrides and missing context/daemon identity refuse. Refusal tests
check that no later daemon read occurs where admission already failed. No daemon
or provider is contacted by these unit cases. Real mounted-daemon/controller
checks remain in the existing full image witness, without assertion changes.
