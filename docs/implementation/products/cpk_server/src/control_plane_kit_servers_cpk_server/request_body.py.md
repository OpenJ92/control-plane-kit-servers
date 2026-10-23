Source: [request_body.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/request_body.py).

The product-local collector accepts an async bytes stream and an inclusive byte
budget supplied by a validated route or the fixed MCP envelope constant. Before
each bytearray extension it compares the incoming chunk length to the remaining
allowance. Overflow raises only RequestBodyTooLarge with fixed text; it does not
append that chunk, pull another chunk, log data or wrap unrelated exceptions.
Cancellation therefore propagates. HTTP and MCP callers map overflow to their
fixed 413 response.

The MCP envelope budget is 1,048,576 actual incoming bytes. Content-Length never
controls acceptance. Final conversion to bytes is another bounded allocation;
the guarantee concerns bounded owned accumulation, not a single-allocation peak,
zeroization, upstream ASGI allocation, JSON object memory or network timeouts.
Direct ASGI tests prove inclusive bounds and no trailing pulls; source review
establishes check-before-append ordering.
