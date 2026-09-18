# Gateway application and process composition

The application constructor receives explicit optional probe verifier and health
relay dependencies. No implicit probe credential lookup occurs there. Health-only
composition has no `/cpk/probes` route; complete explicitly configured probe
credentials retain the old authenticated closed probe route independently.

Production main always loads both required health files, requires port8000, and
then considers the legacy probe-auth environment. All legacy fields absent means
health-only serving; any present field requires the complete valid old set.
Startup failures are bounded and omit candidate context. Access logging is
disabled so query-bearing rejected requests are not copied into process logs.
Minimal own-health endpoints remain liveness/readiness status only.

Historical image descriptors are unchanged. This source process requires the new
health configuration contract; #191 must associate a verified image before any
published deployment can claim it. Gate: existing owning Docker ./test.sh via
ordinary PR CI. Exact source/test head ba9bc249 passed full run35379205171;
[evidence](https://github.com/OpenJ92/control-plane-kit-servers/pull/216#issuecomment-5734352881)
records26 support/436 package tests and existing runtime witness/cleanup limits.

The optional legacy route is transitional only. The user requires all legacy
routes, wiring and documentation to retire before parent1813 is complete; probes
are not a final supported path or a health fallback. This focused slice preserves
that retirement obligation without claiming the old route is permanent.
