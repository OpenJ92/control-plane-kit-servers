# HTTP multiplexer

The primary owns the application response. After primary success, configured
observers receive copied requests sequentially before that response is sent.
An ordinary observer failure does not stop later observers or replace the primary
status/body/content-type. Primary failure, including an HTTP error, timeout or
oversized response, produces fixed502 and skips observers. Observer failures
are best-effort and can add latency; there is no queue or durable delivery record.

Startup reads MULTIPLEXER_PRIMARY_URL and optional MULTIPLEXER_OBSERVER_A_URL /
MULTIPLEXER_OBSERVER_B_URL. Blank observer slots are absent. Immutable settings
capture the URLs; handlers do not reread environment. Only None selects ambient
settings; an explicitly supplied empty mapping is invalid. Production PORT must
be8000, while explicit standalone settings/loopback test addresses remain possible.
The two production environment slots do not limit valid standalone observer tuples.

Forwarding preserves method/path/query/body and ordinary application headers;
Host, Connection and Content-Length are rebuilt. Redirects remain disabled.
Each upstream call has a five-second timeout. Primary response reads are capped
at1MiB and observer reads at16KiB. These are per-call limits, not an overall
request deadline or bound on application body sizes/concurrency.

## Authenticated control

The SDK reserves `/__control` before either forwarding lane. Static capabilities
use separate authority from health reads. Signed `/__control/health/liveness`
reports local process liveness without primary or observer calls. Readiness is
unadvertised: canonical `/__control/health/readiness` cannot report healthy and
never forwards. Unknown reserved `/__control/health/ready` also remains internal.
No upstream probe, target switching, variable or mutation command is configured.

Legacy `/health/live` remains local and public. Ordinary `/health/ready` is normal
multiplexed application traffic. Application Authorization is copied as before;
SDK credentials on protected routes must reach neither primary nor observers.
Liveness says nothing about upstream/observer availability.

## Receiving configuration and evidence

Wrapped source requires trusted `/etc/cpk/multiplexer/control.json` before binding.
The local configuration module provides MultiplexerControlConfiguration,
multiplexer_control_configuration_artifact(config), and
multiplexer_source_runtime_contract(artifact). These use actual Core values and
separate purpose-typed static/health SDK public snapshots.

The closed multiplexer-control-configuration.v1 document contains target,
runtime_id, fixed V2 declaration, surface_read and health_read. Each family has
issuer and1–16 public keys; local audience derives from target. Duplicate/unknown
members, invalid locality/trust and inputs beyond65,536 UTF-8 bytes fail closed
with fixed errors. Never put private keys or bearer tokens in this public file.
The reader checks the opened regular descriptor, rejects final symlinks and
cannot block on a FIFO. Parent-directory integrity/authorized delivery are
prerequisites; parsing does not establish provenance.

The actual source artifact is JSON/0444 with Core-computed digests. The source
contract preserves required primary, both optional observer requirements,
internal8000 and the historical one-check/five-attempt liveness policy. The exact
standard ThreadingHTTPServer is unbound until SDK installation; product code owns
bind/activate/serve/final close and closes failed construction stages.

The generated Dockerfile installs canonical SDK[verification], remains Python3.12 /
UID10004, and contains no default trust. Historical descriptor/catalogue/image
coordinates remain unchanged. Owning ./test.sh source evidence does not qualify
a new multiplexer OCI or prove producer delivery/gateway acceptance. Core1821 /
Interpreters149 own authorized identity and artifact delivery; Servers191 owns
candidate image qualification. The separate legacy multiplexer image smoke lacks
control configuration and uses fixed-name cleanup; do not use it as wrapped
candidate evidence. Its qualification plan needs explicit receiving configuration
and owned cleanup. This source slice neither runs nor repairs that script.
