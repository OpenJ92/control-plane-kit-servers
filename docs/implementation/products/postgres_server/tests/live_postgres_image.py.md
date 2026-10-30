Source: [live_postgres_image.py](../../../../../products/postgres_server/tests/live_postgres_image.py).

The original source-built ladder also accepts an explicitly borrowed published
artifact. Selection precedes fixture creation; all containers use the resolved
immutable ID. The lifecycle/retained-row checks and native-listener-before-SQL
ordering remain shared. Resource cleanup is inside exercise's finally; borrowed
fixture cleanup and ownership-aware image cleanup complete before success output.
Borrowed images are never removed, including on failure. Source image deletion
additionally checks the tag still identifies the owned image.
Before fixtures or lifecycle effects, existing named or labelled containers,
volumes and networks refuse without adoption or cleanup. Only newly returned
objects from the admitted invocation enter cleanup lists.
After image reload, lifecycle admission accepts omitted, null or empty-list
entrypoints, matching initial published-artifact admission. Nonempty and malformed
entrypoints still refuse before network, volume or product-container creation.
See [artifact procedure](../../../../managed-postgres-artifacts.md).

The existing capped failure tail also projects a numeric refused lock PID from
one strictly parsed native hint. States are absent, one, ambiguous, invalid,
truncated or unavailable; only one carries a PID. Parsing requires printable
ASCII, a bounded line and decimal PID range, the data-lock refusal marker and
the exact hint grammar. One adjacent native FATAL/HINT pair must use the supported
UTC timestamp/emitter prefix and the same emitting PID. Embedded/copied hints,
different emitters, reordered/unassociated records and unsupported formats refuse
projection; multiple refusal or hint records never select one. Reaching the requested
128-line tail limit conservatively reports truncated because prior hints may
have been omitted; byte truncation also forbids a unique PID claim.

No raw hint, directory, argv or environment is emitted. This is a projection
of a message, not observed liveness, ownership or root cause. Parser errors retain
the original assertion and cleanup paths. No new process, thread, Docker call,
stderr pipe or product instrumentation is added.

#359 retains `native_lock_emitter_pid` from the already validated matching native
FATAL/HINT prefix alongside `refused_lock_pid`. Only status `one` carries the two
bounded integers; absent, invalid, ambiguous, truncated, unavailable and scanner
failure leave both null. Equal values remain honestly represented rather than
rejected using an unverified assumption about the selected native build.

A differing pair rules out simple equality of the emitting PID and the PID named
in that observed hint. It does not identify PID7's live owner, a reused namespace
identifier, a wrapper thread or another postmaster, nor establish PGDATA ownership
or safe lock removal. Exact native version/entrypoint association remains a
separate evidence gap for failed PR358 run41011530872. Historical #277 acceptance
preserved unexplained recovery uncertainty; this field does not fix recovery.

The existing parser/projection tests cover numeric distinctions/bounds, all null
states, redaction and preservation of the original assertion/cleanup. No new log
read, process, thread, timing, native behavior or recovery assertion is introduced.
Source validation does not release a recovery rerun. Do not loop on emitter-only
sampling: after any separately authorized observation, record the comparison and
stop if instantaneous PID/TID ownership still requires a separately reviewed
observation or explicit uncertainty disposition.
