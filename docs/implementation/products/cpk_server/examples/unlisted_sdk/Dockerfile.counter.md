Source: [Dockerfile.counter](../../../../../../products/cpk_server/examples/unlisted_sdk/Dockerfile.counter).

Counter is an external SDK example/test workload, not a production catalogue
family. The image contains only the two example files and pinned SDK #61
d4e7c4d91c054f139e2971774ae5e37fc741262d with verification extras; SDK selects
Core9861e536e79314005499ae07379f627bfb1599a2. Python3.12-slim is pinned to the
actual successful CI-resolved index
sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1.
Read-only registry inspection selected exactly one Linux/amd64 manifest,
sha256:2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe.
Both source gate and producer explicitly build Linux/amd64. Transitive installed
dependency versions are recorded in actual build evidence; the producer rebuild
and its uploaded/pulled artifact still need separate qualification.
Numeric UID10008 serves private8000 and reads the declared wrapper path. No
credentials, controller package, runtime installation, host port or daemon mount.
Source gate owns its labelled build tag and cleanup; separately authorized
publication rebuilds and requires actual pulled-digest qualification afterward.
