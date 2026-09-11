Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This collector combines explicit local invocation references with selected
public read envelopes. It accepts one to four unique canonical UUID4 operation
references and checks each journal target against the profile's workspace and
endpoint digest. File/saved/catalogue requested provenance stays distinct from
server-reported session metadata, immutable draft association, plan/approval,
run events and the separately read latest overview.

The read allowlist uses the operator role, at most 32 calls, one page per
collection, two runs per plan and ten events per run. A 60-second scheduling
budget is checked before calls; it does not interrupt a slow in-flight request
or impose a whole-operation wall-clock deadline. Nonempty next cursors become
truncation instead of pagination. Envelope/workspace/foreign-key and duplicate
event/run checks protect association; a matched draft graph is not a provider
observation or deployment success.

Sections retain observed, mismatch, unavailable, truncated and not-applicable
states. Authorization refusal propagates rather than becoming a generic
unavailable section. Pending journal requests remain transport-unresolved.
The top-level status is attention-required when collection has issues;
observed means evidence collection succeeded, even when a reported run status
is a failure. The result explicitly says atomic_snapshot=false and
provider_freshness=unknown.

Projection selects bounded identifiers and closed statuses, omitting graph
payloads, titles, raw event payloads, credential material and replay keys from
the ordinary envelope. Selected text fields are not universal secret
detectors. Output over 256 KiB collapses sections to explicit truncation;
the CLI separately bounds actual encoded output including its newline.

The collector sends no command route and rewrites no invocation record.
JournalStore.read does call initialize, which can create missing state
directories: absence of report writes in the existing-journal test is not a
promise of zero filesystem effects for every invocation. This owner supplies
neither an atomic server snapshot, fresh provider truth nor recovery authority.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py), [products/cpk_server/tests/test_topology_client_report.py](../../../../../../../products/cpk_server/tests/test_topology_client_report.py).
