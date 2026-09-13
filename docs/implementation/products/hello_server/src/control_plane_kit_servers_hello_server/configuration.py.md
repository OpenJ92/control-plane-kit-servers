Source: [configuration.py](../../../../../../products/hello_server/src/control_plane_kit_servers_hello_server/configuration.py).
Maintain with the Hello receiving ABI and source contract.

Hello owns a closed public configuration document, not an issuer or generic SDK
configuration language. Local target references use Core's actual roles, runtime
uses RUNTIME, and the declaration must equal Hello's fixed internal-socket V2
liveness/readiness surface. Static and health key families have different nominal
SDK snapshot types/purposes; audiences derive from the supplied target. None of
these values comes from incoming credentials. At most 16 keys per family and
65,536 total UTF-8 bytes are accepted; malformed/duplicate/unknown input fails
with a fixed cause/context-free error. Key-shape validity does not prove issuer
provenance or cryptographic attestation.

Ordinary decode/render/read failures are translated to a fixed product error and
raised after leaving the exception handler. Validation exceptions set the actual
rejection flag. No empty exception handler, raw error attachment or BaseException
capture is used; process interruption propagates. The owning tests check error
chain absence across decoder/file/artifact/contract boundaries.

The fixed-file reader opens with NOFOLLOW/NONBLOCK, checks regularity on that
descriptor and reads at most 65,537 bytes before close. It does not check a path
then reopen it. The parent directory and public file delivery are trusted local
composition prerequisites; reading a regular file does not establish provenance.

The pure renderer emits Core ConfigurationArtifact with hello-control ID, fixed
/etc/cpk/hello/control.json path, JSON media and 0444 mode. It computes digests
through Core and revalidates the receiving byte limit. The source runtime-contract
factory adds a required actual artifact, internal HTTP8000, existing environment
defaults/legacy verification, explicit NODE_CONTROLLABLE and HEALTH_CHECKABLE,
and the fixed surface. It neither registers nor publishes a descriptor. Historical
product.cpk.json and catalogue remain unchanged; #191 qualifies a future image.
Operations selected-artifact delivery/identity production belongs to #1821/#149.
