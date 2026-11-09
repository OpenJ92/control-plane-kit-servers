Source: [test_packaged_sample_fixture.py](../../../../../products/cpk_local_gateway/tests/test_packaged_sample_fixture.py).
Governing work: [Servers #163](https://github.com/OpenJ92/control-plane-kit-servers/issues/163).

Unexecuted source candidate. Three tests check the preparation boundary: exact
original live/ready bindings, public-only0444 artifacts and collision refusal;
an isolated purpose-only transit negative preserving its other authority fields;
then real gateway HTTP/V2 ASGI handlers with explicit external child HTTP reply
doubles. Real gateway transit admission, structural pairing, forwarding and
response codecs run. The double validates each outgoing workload signature
against its independent public key and returns explicit Core result values.
Non-reflecting Boolean assertions inspect the entire outbound request: exact
fixed URL, GET, empty body/query, one workload Authorization and exactly the
allowed headers with their expected values. An additional header, bearer value,
query parameter or body fails without reflecting it in assertion output.
It does not emulate a child SDK authorization decision or health callback.

Eight HTTP forwards are expected: four positive requests and four matching
foreign-workload-issuer requests. Other refusal cases must add none. Two V2
LIVENESS forwards are expected; cross-family transit must add none. Counts and
public signature booleans are test-local observations, not packaged-image
claims. No authorization string is retained. The packaged controller explicitly
reports that forwarding and child health-probe instrumentation are absent.

Full product discovery includes an existing test that unloads gateway modules
between cases. Resolve gateway-family imports at fixture construction and relay
test invocation, preserving current exact-type identities after those unloads.
No production identity check or existing test cleanup is relaxed.

Owning execution must be integrated by Lin through `./test.sh` using its selected
cached controller and required policy/integrity phases, with no new image build
for the source-only phase. Until that gate runs, these tests have no green evidence.
Preserve existing gateway relay suites and full-suite discovery. No Core or
Operations stores, histories or state machines are recreated by these tests.
