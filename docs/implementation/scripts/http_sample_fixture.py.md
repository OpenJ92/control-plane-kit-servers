Source: [http_sample_fixture.py](../../../scripts/http_sample_fixture.py).
Maintain alongside both source image smokes.

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
