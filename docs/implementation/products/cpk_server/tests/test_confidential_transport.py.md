Source: [test_confidential_transport.py](../../../../../products/cpk_server/tests/test_confidential_transport.py).

#316 target tests use the real FastAPI app and explicit ASGI receive frames, with
the existing effectful service factory replaced by recording services. This proves
chunk reads and stopping behavior without TestClient coalescing. Assertions cover
404/401 before receive, one authentication, exact route byte budgets, absent/false
Content-Length, UTF-8 split across chunks, no trailing pull after overflow, GET
body/command query precedence against the byte API, MCP 1 MiB inclusion/overflow
and below-cap header/auth/parse order. Maximum reobserve frames use the existing
65,536-byte transport framing budget with escaped and unescaped Unicode; no
semantic Operations acceptance of large identifiers is claimed.

Neutral poison Mapping tests prove HTTP-only route refusal before arguments are
retrieved, and standard request repr must omit a synthetic confidential sentinel.
Raw JSON parsing follows authentication and precedes that neutral check; these tests do not
claim raw JSON cannot exist in memory. Existing bounded error/conflict/status
forwarding is exercised with recording services, not duplicated attempt logic.
The separate default-composition case uses the real production factory and
synthetic configured operator, replacing only schema/database effects, to require
provision 501. Cancellation remains cancellation, not overflow.

#341 updates only below-cap MCP framing precedence to the selected authenticate-
before-sensitive-decoding contract: missing headers refuse first, rejected
credentials refuse before malformed JSON, and admitted malformed JSON returns
400 after exactly one authentication. The preexisting inclusive envelope cap,
overflow/no-trailing-pull, confidential-route exclusion and zero-dispatch laws
are unchanged. This source update awaits owning-gate validation.

Test-only commit 30b809f ran in normal CI 40020316825: 612 CPK methods,
19 assertion failures across eight new methods, with no collection/fixture error
or unrelated failure. Four whole methods preserved existing behavior. Exact
assertion reach and checkout identity are recorded in PR #320 comment 6374259741;
assertions after each failure and later gate stages receive no red evidence.
The subsequent source implements these missing protections without changing the
target tests. Green validation remains pending. No provider call, image/live
qualification or confidential intake enablement is supplied. Only unchanged
./test.sh/PR CI is used. Repr omission does not make asdict/arbitrary serialization
safe, and bounded owned accumulation is not a network timeout or upstream ASGI
allocation bound.
