Source: [packaged_sample_fixture.py](../../../../../products/cpk_local_gateway/tests/packaged_sample_fixture.py).
Governing work: [Servers #163](https://github.com/OpenJ92/control-plane-kit-servers/issues/163).

Source preparation only; this candidate has not run. One controller lifetime
creates public receiver artifacts for CPK, Secrets and their gateway while five
independent fixture signing keys remain in memory. A fresh directory and fresh
receiver IDs prevent accidental reuse of a prior cleaned installation. Product
renderers supply the original CPK Docker/Cloudflare and Secrets contracts,
including both named HTTP live and ready checks. Their common workload HTTP
verifier differs from the gateway HTTP transit verifier. Generic V2 workload
health, gateway health transit and control-surface trust remain separate.

The controller writes public artifacts and a prepared marker, waits at most120
seconds for its owner's ready marker, then makes actual owned-network requests.
Four HTTP sample responses must satisfy the original request/check canonical
codec, PASSED outcome and status200. Missing, foreign-issuer or wrong-purpose
transit refuses401; unknown/crossed selectors and mismatched workload target or
check refuse403; expired transit/workload refuses504. A structurally matching
foreign workload issuer reaches the fixed child verification endpoint and its
401 becomes gateway502 in the explicit unit double. A packaged outer502 alone
can also mean transport/protocol failure; its receipt records that status and
leaves forwarding and child refusal unobserved. No refusal row infers a path
from status alone. Each refusal mints fresh control credentials immediately
before dispatch. Wrong transit purpose retains the transit signing key, issuer,
audience and token type, changing only the grant purpose (plus fresh token ID).

Separate generic V2 LIVENESS exchanges cover both existing child declarations.
HTTP transit on the V2 route and V2 transit on the HTTP route must each refuse401.
The named HTTP ready check does not introduce generic V2 READINESS. No SQL
readiness, Operations registration, run, durable history or provider authority is
invented. Child health-probe counts and outbound bearer identity are not observed
by this black-box controller and are labeled accordingly in its public receipt.

Controller entry point inside the owning Docker gate is
`python products/cpk_local_gateway/tests/packaged_sample_fixture.py /fixture/public`.
The caller owns the fixed gateway-source:8000, cpk-source:8080 and
secrets-provider:8081 aliases, image identity, read-only artifact mounts, actual
readiness, observed helper exit0, and exact owned cleanup. It must keep the
controller alive from artifact preparation through signing; private keys cannot
be regenerated between those steps. The240-second process alarm bounds the
whole controller. No automatic retry exists. Fixed failure output excludes
tokens, peer bodies and exception details. Source or image failure stops the
owner; this helper is not release authority or an alternative test runner.

No product source, dependency pins, Dockerfile or root test selector changes in
this candidate. Lin owns the execution packet and selector integration. Source
tests must enter through the established Docker-backed `./test.sh`, retaining
normal full-suite discovery. Packaged acceptance requires separately reviewed
actual gateway and child images; ASGI tests cannot establish it.
