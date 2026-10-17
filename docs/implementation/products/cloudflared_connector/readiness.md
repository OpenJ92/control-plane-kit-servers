# Native connection sample

Source: [readiness.py](../../../../products/cloudflared_connector/src/control_plane_kit_servers_cloudflared_connector/readiness.py).
Owner: Servers #228 under #188; future consumer Interpreters #148.

`classify_response(status, body)` maps the pinned native `/ready` response to a
`ConnectionSample`. `read_connection()` performs one fixed numeric-loopback read;
`main()` emits its compact JSON and returns0 only for connected. The native
status and count must agree (200/positive or503/zero), with exact fields, integer
uint64 count and a canonical non-nil connector UUID. Otherwise evidence is
unknown. The observed UUID is provenance, not an invented expected identity.

The local HTTP reader requires Content-Length, rejects transfer/compression and
redirect semantics, and caps total status/headers at8192 bytes and body at1024.
One monotonic2-second deadline covers connect, request, headers, body and final
classification. Each blocking operation receives only the remaining duration.
The pinned Go handler's small buffered response supplies Content-Length; an
upstream framing change must be reviewed, and meanwhile becomes unknown.

Only the following unknown reasons are emitted: invalid_response, invalid_http,
response_too_large, timeout, transport_unavailable, invalid_invocation. Output
from the reader contains only bounded schema/outcome/reason or validated native
count/UUID; no body, exception, URL, log or environment. The fixed input and
256-byte output are product contracts, not configurable probe infrastructure.

The source Dockerfile copies the exact pinned native binary into Python3.12-slim,
uses65532:65532 and keeps cloudflared as direct PID1 with SIGTERM. The metrics
listener is fixed127.0.0.1:20241 and has no declared/published port. Its other
native diagnostic routes are not a network service offered to the graph.
Docker schedules the packaged command every5s with3s outer timeout and1 retry.
Its aggregate health status is not connection truth.

The normal test.sh builds this source image and invokes the packaged witness in
an isolated network-none container. The witness verifies actual Config, UID,
native version/exit and synthetic0400/000 permissions; its controlled loopback
fixture exercises connected/disconnected/unknown CLI results. It disables
scheduled checks only in that fixture container to avoid competing test clients.
Image configuration proves the direct signal path, not observed native shutdown.
No live tunnel, Cloudflare request, provider token or image publication occurs.

Same-UID code may technically access a mounted token. This reader intentionally
does not accept/read it; that is not isolation from arbitrary container code.
Published descriptor/catalogue images remain historical. Persistent SDK control,
bidirectional native/wrapper failure and runtime signal/shutdown evidence remain
mandatory #188 work. #148 must validate exact ownership/image/configuration,
incarnation, latest sample and original authority/time before accepting evidence.
