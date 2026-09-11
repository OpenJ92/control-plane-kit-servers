Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/cli.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This entrypoint parses a named profile and delegates plan/apply/status,
overview/draft operations and finite reports to TopologyClient. Plan accepts a
file, saved revision or invocation resume, with draft/revision required
together. Apply requires an exact --execute-plan argument and offers mutually
exclusive ordinary/destructive approval flags; the workflow checks those
values against server-reported plan/approval truth. Argument presence alone is
not authentication or authority.

Draft selectors use canonical positive integers and a bounded object cursor.
Reports render the same envelope in human/JSON modes, falling back from
indented to compact JSON when necessary and counting the trailing newline in
the output ceiling. Other result types have their own projections and output
shapes; the report-specific ceiling is not imposed universally.

Known authorization errors return 3, input errors 2, and configuration,
journal or transport errors 5; ordinary results supply their own exit code.
The renderer prints the selected exception message, not a general sanitized
trace, and argparse failures follow argparse's own behavior. The CLI owns
syntax and presentation, while workflow/journal/transport own command
sequencing, persistence and HTTP effects. Its role as a product entrypoint
does not change the repository's executable-validation rules.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py), [products/cpk_server/tests/test_topology_client.py](../../../../../../../products/cpk_server/tests/test_topology_client.py), [products/cpk_server/tests/test_topology_client_report.py](../../../../../../../products/cpk_server/tests/test_topology_client_report.py), [pyproject.toml](../../../../../../../pyproject.toml).
