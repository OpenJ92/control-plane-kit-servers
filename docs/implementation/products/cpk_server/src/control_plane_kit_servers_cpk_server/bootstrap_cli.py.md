Source: [bootstrap_cli.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py).

#302 selects the verified plan's setup_products for the enabled complete profile;
otherwise public_setup uses the original installation.products.values() path.
The existing command sequence, exact ProductReference verification, durable
progress and bounded result projection are unchanged. Credential arguments are
absolute private-file Paths consumed by the real ClientProfile, not bearer text.
An interrupted fourth import leaves pending progress; a returned mismatched
reference cannot complete setup. This source change does not qualify serving
images, establish external readiness or add credentials/runtime access to the
website.

#346 exposes fixed-input initialize-workspace and inspect-workspace-initialization
helper subcommands, without database/schema/actor override flags. The separate
inspect-initialization controller requires the reviewed plan/driver/digest,
private index and existing state. Ordinary setup stays static until #347 adapts
its public administration protocol; the full dynamic-apply guard remains.

#347 adds a dynamic path: re-admit the fixed private intent and actual bearer before
transport construction, progress creation or readiness. Administration and grant
commands carry reviewed explicit keys and actual owner payloads; reads use the
existing public query encoder. Management is sent only after exact registration
response/readback. The receipt provides current-graph attribution; final workspace
read supplies desired graph, and both graph reads must agree. Static setup keeps
its legacy route and direct-call error behavior. Dynamic failures drop private
exception context. Returned safe coordinates are persisted before later validation;
an acknowledged response is not a verified readback or completion.

The first local component gate exposed an overstrict desired-graph assumption:
fresh creation initializes current only. Dynamic completion accepts an explicitly
null desired ID only with an unassigned desired read, and otherwise requires the
matching assigned ID. Static comparison retains its prior optional-ID semantics.
