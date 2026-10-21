Source: [test_root_bootstrap_diagnostics.py](../../../../../products/cpk_server/tests/test_root_bootstrap_diagnostics.py).

The existing diagnostic tests protect closed bootstrap failure projection and
numeric identity observations. The #301 correction adds three tests at the
actual-driver subprocess reporting boundary: each ordered stage prefix reports
only its fixed last stage, arbitrary/private/malformed output reports unknown,
and success requires zero exit plus the complete ordered witness. Child stderr
is discarded even when it contains private canaries. Existing tests and the
owning Docker-backed test.sh remain unchanged.

#302 extends each ordered stage expectation with complete-plan, retaining the
existing six stages, private-output refusal and exact zero-exit success law.
