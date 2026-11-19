# Finite retained-ingress reader (#221 Stage A)

`gateway_ingress_admission.py` composes the existing protected-file reader and
Cloudflare API client for four fixed GETs: the exact hostname's DNS records,
the independently expected tunnel, its connections, and its configuration.
Expected hostname/tunnel are comparison inputs, not inferred ownership.

The new transport permits only those four URLs and GET, with no request body,
redirect, retry, environment proxy or token endpoint. TLS verification remains
enabled. Each response has a 64 KiB cap, ten-second I/O timeout and twenty-second
elapsed check during/after streaming; this is not a hard wall-clock deadline.
The concrete invocation also needs bounded outer supervision. No successful live observation is
claimed by tests. The existing provider owns auth/status handling; its private
`_request` is used narrowly for these reads and is a selected-version dependency.

Credential loading uses bounded regular-file/no-follow/owner/mode checks already
used by the diagnostic. Only the four known literal assignments are parsed;
there is no shell execution or variable expansion. Tokens and provider bodies
never enter public output. Protected mount/parent integrity remains an invocation
responsibility, including keeping input files unchanged during the observation.

Admission requires one exact proxied CNAME, one matching live remote-configured
tunnel and zero connections. Only an exact-host HTTP origin followed by a404
catch-all is accepted, without path matches, origin overrides or enabled WARP.
Unrecognized routing shapes stop instead of gaining new semantics. This is a
point-in-time compatibility observation, not origin reachability, exclusive use,
a lease, token validity or permission to start/repoint a connector.

The receipt contains the exact record/tunnel identity, origin and timestamp;
it is created exclusively as a private file in a private owner directory. Existing
files are never overwritten. Partial write uncertainty leaves the file for review.
Stdout contains only categorical status, hostname, zero observed connections and
timestamp. Failure prints one fixed status, never raw exceptions.

Execution uses the frozen369b `Dockerfile.test` controller, whose package includes
both the CPK and gateway codecs required by the shared reader imports. The CPK
product image is insufficient. Build the controller once only after source/owner
review, record its immutable ID, and mount the exact reviewed new module as a
read-only artifact; do not build from the changing artifact branch. Stage A runs
as the host's recorded numeric UID/GID so the existing mode0600 input and new
mode0700 output directory retain their ownership, without permission widening.
It receives no Docker socket, tunnel-token volume or other private input.

Command inside that controller (explicitly overriding its default test command):

```
python /run/admission/gateway_ingress_admission.py --env-file /run/admission/credentials.env --receipt /run/admission-output/receipt.json
```

The mounted module is executable directly and uses the installed frozen package
for existing owners. Only the output directory is writable; source and credential
mounts are read-only. The exact outer Docker command, source hashes, private output
path and image identity are reviewed before this live read. No build, image push,
connector start, Cloudflare change, token read, database write or key generation is
performed by this module.

Nine new-law methods in `test_gateway_ingress_admission.py` cover the four-read
path through both the owner protocol and actual bounded HTTP adapter, early DNS/
tunnel/connection refusals, local/global origin overrides, protected literal input,
transport bounds and private exclusive output. Causal-red at2e570222 ran through
ordinary CI35930642259: nine missing-interface failures, no errors; deeper cases
require unchanged full green. Tests use synthetic credentials and mock HTTP only.
