Source: [products/cpk_server/tests/test_topology_client_report.py](../../../../../products/cpk_server/tests/test_topology_client_report.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

These tests build local invocation journals with scripted public transport
envelopes, then exercise report collection. They distinguish file/saved/catalogue
provenance, immutable revision association and the separately read latest
overview, asserting only read routes/operator credentials and unchanged
existing file bytes during the report.

Negative cases cover foreign or missing correlations, absent history,
uncompensated failure status, page cursors, scheduling exhaustion and invalid
reference sets. They require explicit uncertainty/truncation rather than
convergence. Selected sensitive graph/title/event fields are omitted; that is
a projection witness, not a universal secret scanner or a real auth service.

Maximum-shape and Unicode cases exercise envelope truncation and CLI output
limits, including the trailing newline and compact fallback when indented
output would overflow. Scripted setup commands create test journals before
the reads; no live CPK or provider is contacted. The no-file-change assertion
uses an already initialized journal and does not cover directory creation on
a fresh state root.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py](../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py), [products/cpk_server/tests/test_topology_client.py](../../../../../products/cpk_server/tests/test_topology_client.py), [products/cpk_server/tests/test_topology_client_catalogue.py](../../../../../products/cpk_server/tests/test_topology_client_catalogue.py).
