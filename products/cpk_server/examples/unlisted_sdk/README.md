# Independent SDK receivers

`counter.py` serves a changing integer at `/count`; `palette.py` serves a small
static document at `/palette`. They are independent application examples and
import only Python's HTTP host and the standard SDK wrapper. Neither imports
Hello, the controller, Operations, a product catalogue or another example.

The SDK reads `CPK_WRAPPER_CONFIGURATION_FILE`, a delivered absolute regular
`0444` file. Its common configuration carries the receiver identity, declaration
and public verification keys. The application supplies no health callback: the
SDK reports its own serving lifecycle. This is availability of the HTTP host,
not proof of a database or application dependency's readiness. These examples
bind loopback and announce their assigned port for the maintained source witness.

The normal repository `./test.sh` stages these files into the existing CPK smoke
container after freezing its controller image. The witness registers two distinct
product declarations, invokes the authenticated client's receiver-authoring mode,
and delivers the exact committed effect material. Lost preparation response retry
uses the persisted graph without generating another receiver identity. A stopped
and waited child is restarted with unchanged bytes, then receives another actual
signed SDK health call. There is no controller dispatch entry or per-product
controller rebuild.

The loopback process runtime and logical-host-to-loopback mapping are explicit
test substitutes. Product descriptor image references are never executed or
published. Gateway ASGI transport and synthetic external ingress remain inherited
fixture boundaries; this is not production Interpreters wiring, published-image
qualification or a live grandparent run. Use the owning gate rather than launching
this composition with a separate host script. Image/config/key/declaration update,
physical configuration custody and delete/reinstantiate obligations remain in
#237's acceptance map and the existing downstream issues.

`counter_container.py` is a separate private container entrypoint for the same
Counter handler and real SDK host. `Dockerfile.counter` pins accepted SDK #61
(`d4e7c4d91c054f139e2971774ae5e37fc741262d`, selecting Core9861e536), runs
as numeric UID10008, and listens on port8000. Supply the public wrapper artifact
read-only at `/etc/cpk/counter/control.json`; no host port, private signing key,
controller credential or Docker socket belongs in this workload. The original
loopback entrypoint remains unchanged.

Normal `./test.sh` builds one Linux/amd64 source image and exercises it with
readiness-only and liveness+readiness V2 configurations in the existing private
numeric-bootstrap fixture. It checks signed capabilities/health, refusal of
undeclared liveness, credential/target failures, `/count`, installed public bytes,
nonroot execution, selected SDK/Core provenance and exact owned cleanup. Default
SDK lifecycle remains the health meaning. This proves source startup, not a
published immutable image or the coupled Operations transition.

The closed `counter-witness` case in `scripts/publish_product_image.sh` uses the
existing manually dispatched producer and explicit Linux/amd64 build. It does
not add a production catalogue family. Publication needs a separately reviewed
source/build/destination packet and authorization. The producer rebuilds: an
earlier source image ID is not proof of the uploaded artifact. After authorized
push, record the genuine registry digest and qualify the actual pulled artifact
before using it for #254's two registered revisions. No registry digest or
destination visibility is asserted by this source change.

Private publication uses a dedicated `counter-witness-264-<source-prefix>` tag
inside the existing private `cpk-server` package. This is a storage exception:
the image is still Counter, not a controller product or catalogue variant.
Provider checks require the exact existing package to be private before and
after push; publication refuses an existing tag. Use the real resulting digest
with the explicit counter fixture role, never a production cpk-server tag or the
package's newest version. Never delete the shared package; separately approved
version cleanup must refuse unrelated tags or ambiguous ownership.

The preload accepts a future exact `counter` record only after actual approved
publication. No such record is invented here. Existing four-image checks remain
their existing evidence; they do not prove the counter's required coupled update.
