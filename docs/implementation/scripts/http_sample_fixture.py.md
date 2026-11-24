Source: [http_sample_fixture.py](../../../scripts/http_sample_fixture.py).

The CPK and Secrets source image smokes each supply their installed control
snapshot and product runtime contract. The witness requires exactly the declared
live and ready checks. It binds each check's digest in the public sample
configuration and keeps the synthetic signing key in memory. Receiver tests can
still select ready alone.

After the owning smoke signals listener readiness, the witness signs a fresh
15-second grant for each check and sends it once to the original product
listener. It requests identity encoding and reads at most 2048 raw bytes per
response. Core decodes the canonical bytes against that request and check.
Both responses must have HTTP 200 and correlated inner PASSED evidence with
status 200 before the witness writes its success marker. Failure output is fixed.

The witness waits up to 120 seconds for readiness and has a 150-second process
deadline. After signaling readiness the parent allows 30 seconds for both
exchanges and requires an observed successful exit.
