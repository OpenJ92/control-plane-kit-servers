# Managed connector coordinator

Source: [coordinator.py](../../../../../../products/cloudflared_connector/src/control_plane_kit_servers_cloudflared_connector/coordinator.py).

Servers #188 next slice after merged PR278/34bdd422. Current file is an intentional
NotImplementedError scaffold for focused causal-red targets, not an implemented
entrypoint. The reviewed product-local process-owner interface is
`run(configuration, *, token_path) -> int`. Private launch and raw diagnostic
helpers expose effect boundaries to targets; they are not a public supervisor API.

Frozen plan SHA2569f517197510a53cb4af9920082bc4c1508647ae3ebec00d2f7d46a71aac7e1ec
has actual Kepler and Meridian PLAN PASS. Validate before effects, use one native
process group and common SDK host, preserve first-stop7/8s deadlines and explicit
failure/forced-cleanup precedence. Exact child environment contains only the
validated token path. The optional raw diagnostic sink accepts an already
nonblocking pipe only, never changes shared flags, and may drop all diagnostics.
Token values, candidate paths and raw thread errors are excluded from records.

No-child early stop is a clean cancelled startup when no failure/resource exists;
it does not fabricate native exit0. Target review and owning-harness causal red
must precede source implementation. Image/PID1/profile/actual-process termination
remain later evidence; no publication, provider action or lifecycle guarantee is
claimed by this scaffold. Existing managed.py, reader and historical image stay
unchanged.
