Source: [http_sample_fixture.py](../../../scripts/http_sample_fixture.py).
Maintain alongside both source image smokes.

For #163, optional `all-checks` binds the unchanged CPK Docker/Cloudflare
contract's live and ready checks to one fresh synthetic receiver and one
in-memory sample signer. Each original check gets a distinct request ID and
ordinal one. The Core codec checks the bounded canonical PASSED/status200
response. Each check also requires 401 for absent credentials and for a
cryptographically valid same-key/kid token with foreign issuer in both JWT and
grant. No token is emitted. The public result records these separate outcomes
and the synthetic fixture delta, without claiming an approved child run.
Existing ready-only CPK and Secrets callers retain their behavior. The helper's
alarm bounds its lifetime; the focused parent requires observed exit zero within
45 polls after signalling readiness. Docker CLI polling assumes a responsive
daemon and does not establish a hard deadline for a hung Docker process.

Shared test-only evidence has two consumers: CPK and Secrets. Each supplies its
independent V2 snapshot and original product runtime contract. The fixture
creates ephemeral separate sample trust, renders the product's public artifact,
and keeps its private key only in memory. After a bounded120-second wait for the
owning smoke's actual readiness marker, it mints one15-second grant, sends once
to the named actual product listener and decodes the bounded response against
the exact original request/check. Outer200 is insufficient: inner PASSED and
status200 are required. Fixed failure output excludes credentials and responses.
The helper is not a production signer, relay, retry loop or acceptance harness.

Review correction: read at most Core's2048-byte wire bound and decode the
original canonical bytes with Core, preserving duplicate/noncanonical rejection.
A150-second hard process alarm covers preparation, readiness and the exchange;
parent smokes also bound completion after readiness to20seconds and require
observed exited/status0. No blocked `docker wait` remains.
