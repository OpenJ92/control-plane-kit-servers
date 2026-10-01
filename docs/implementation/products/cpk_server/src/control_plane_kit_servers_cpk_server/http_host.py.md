Source: [http_host.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/http_host.py).
Maintain alongside the public route compatibility contract.

The product derives literal first prefixes from every Core operator route before
mutating the standard FastAPI route list. Root/dynamic/reserved prefixes and
unsupported methods fail rather than silently losing future operator routes.
Exact health/MCP handlers come first; prefix and empty-tail GET/POST routes then
pass original method/path/headers/body/raw query to the existing neutral boundary.
No matching, authentication, decoding or service semantics are duplicated here.

One Starlette HTTPException handler projects application404/405 into historical
unknown-route and method responses. Actual matched405 retains its Allow header;
unmatched unsupported methods receive the prior GET/POST Allow. The decoded ASGI
__control first segment delegates unchanged to FastAPI. SDK returned Responses,
other errors and redirect behavior are untouched. There is no root wildcard,
custom route/router default, post-install bypass or SDK admission relaxation.

Servers199 prepares hosting only. Production create_app still builds the same
services/schema, boundaries, exact health/MCP handlers, then literal routes.
SDK is installed only in owned composition tests. Servers200 owns required
receiving configuration, production SDK installation and ordering before schema
effects. Source-image startup inputs and published descriptors remain unchanged.

Servers200 now consumes this unchanged helper in production SDK composition.
Required receiving admission precedes host construction; SDK installation follows
these literal routes and precedes existing schema/service effects. The historical
Servers199 checkpoint above describes the independent prerequisite evidence.
