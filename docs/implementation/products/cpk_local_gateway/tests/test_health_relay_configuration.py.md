Source: [test_health_relay_configuration.py](../../../../../products/cpk_local_gateway/tests/test_health_relay_configuration.py).
Maintain this companion alongside its source and selected dependency contracts.

# Health relay configuration and startup laws

The #181 adoption uses Operations f1e's target_surface projection field, which
names the same selected workload surface for this case. Edge-free management
socket selection, exact declaration/origin and all negative cases remain intact.

The product-owned target factory receives the actual Operations-selected
management socket and a Core runtime contract, selecting HTTP control8087 instead
of application8080 or SQL5432 without an ordinary consumer edge. Malformed,
missing or ambiguous control material must fail closed. Configuration artifact
framing, strict decoding, duplicate target refusal, cross-file identity, source
transit declaration and historical published descriptor preservation are tested.

The startup witness invokes actual main with temporary selected files redirected
from the two fixed process paths; only file placement and uvicorn serving are
patched. It checks selected B trust instead of default A, both required files,
fixed port8000, optional complete legacy authority, and partial legacy refusal.
There is no container/process deployment or secret-provider call here. Production
configuration generation from admitted Operations context remains #181.

The original target guard separated missing behavior from collection errors.
All configuration/startup laws, including the reviewed fixture corrections, ran
green at ba9bc249 in full owning CI35379205171.
[Exact evidence and limits](https://github.com/OpenJ92/control-plane-kit-servers/pull/216#issuecomment-5734352881).
The optional probe route is transitional: the user requires all legacy routes,
wiring and documentation to retire before parent1813 completion, with no fallback.

#182 supplies the required third gateway-control artifact to the existing source
factory and actual-main fixture. Selected B transit-key, exact slot/path/mode,
fixed port, absent/malformed relay files, legacy-auth independence and historical
descriptor assertions remain. Missing-file cases retain the other two valid
files so startup failure cannot be credited to an unrelated absent control file.
