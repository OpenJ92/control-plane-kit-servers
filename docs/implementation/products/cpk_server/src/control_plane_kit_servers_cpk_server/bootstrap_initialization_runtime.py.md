Source: [bootstrap_initialization_runtime.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_initialization_runtime.py).

#346 composes one helper within the existing acquisition receipt. The mutating
phase requires only the freshly created PostgreSQL container and no pending
acquisition, before application writers. Exact daemon, container/image, labels,
complete data/protected mounts, receipt-owned volume IDs and earlier absence
observations are checked before helper creation and again before its one start.
The selected CPK image supplies the numeric nonroot helper UID. The driver is
immutable; its actual installed schema/Operations coordinate binds the helper.

Only needed private inputs are copied to temporary 0400 volumes. The helper has
no socket, published ports or added capabilities; its root is read-only, /tmp is
bounded, and full protected subpath mount/configuration observations must match.
Create IDs are saved before verification. Progress is read through a bounded
single-file archive and decoded into a closed redacted shape. A wait/readback
failure preserves uncertainty, earlier observations and temporary resources.

Explicit inspect-initialization acquires the existing writer lock before reading
or changing the receipt. Its single nested attempt owns pending/helper/temporary
resource/cleanup observations without rewriting original phase, pending or
initialization evidence. Matching readback cannot erase unfinished cleanup or
permit redispatch. Completed inspection returns retained evidence on repeat,
not a claim of a new provider observation. The helper is read-only to the database,
while creating it is explicitly a bounded Docker mutation.

Only a confirmed completed helper with retained validated readback is eligible
for exact ID/label cleanup. Each removal remains pending until absence is verified;
unknown or foreign resources stop cleanup. PostgreSQL and installation policy
are not cleanup candidates. No compensation, resume, adoption, schema SQL, new
lock owner or generalized recovery is added. Source/controller seam tests are
not full bootstrap or real Docker helper acceptance; owning evidence is pending.
