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

The added counter OCI witness was retired in #272 after #269 established the
same-image, two-declaration source proof with Hello. These original process
examples remain independent SDK examples; they do not require a counter image.
Removing source does not remove any previously published registry artifact.
