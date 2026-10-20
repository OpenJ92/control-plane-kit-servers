# Managed witness failure diagnostics

Source: [test_managed_witness_diagnostics.py](../../../../../products/cloudflared_connector/tests/test_managed_witness_diagnostics.py).

Servers #284 diagnostic plan received Meridian and Kepler PLAN PASS after
gate39381573535 lost the detached helper's specific failure observation.
Five focused methods cover closed reason selection with candidate canaries,
nonzero completion with valid/missing/invalid records, deadline exhaustion
before file opening, unchanged success and zero-exit/failure inconsistency,
and mode-restricted best-effort failure writing.

The tests substitute only result retrieval or record writing at the existing
witness boundary. The deadline case uses the actual reader. They do not model
Docker internals, native lifetime, or SDK behavior. Existing automatic product
test discovery collects them; no collection or skip configuration changes.
No executable validation has run for this correction. Only the owning Docker
`./test.sh` can validate it after source review and North's next run release.
