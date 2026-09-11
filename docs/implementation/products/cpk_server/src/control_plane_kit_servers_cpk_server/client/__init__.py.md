Source: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/__init__.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/__init__.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This facade exports the maintained topology client, file/saved-input values,
profile and transport, invocation journal and projected result types. It
imports their modules eagerly but calls no profile loader, workflow method
or CLI entrypoint itself.

These exports span different owners: a JournalStore is private invocation
provenance, a CatalogueResult is a receipt or selected public observation, and
a ReportResult combines finite non-atomic evidence. None is provider authority
merely because it is exposed through the same client namespace. Read each
owner and the actual pinned public contracts before changing exports or
treating a result as deployment truth.

Related source and evidence: [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/profile.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/transport.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/journal.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/workflow.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/catalogue.py), [products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py](../../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/client/report.py).
