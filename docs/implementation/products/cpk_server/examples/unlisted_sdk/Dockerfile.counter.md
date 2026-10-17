Source: [Dockerfile.counter](../../../../../../products/cpk_server/examples/unlisted_sdk/Dockerfile.counter).

Counter is an external SDK example/test workload, not a production catalogue
family. The image contains only the two example files and pinned SDK #61
d4e7c4d91c054f139e2971774ae5e37fc741262d with verification extras; SDK selects
Core9861e536e79314005499ae07379f627bfb1599a2. Python3.12-slim is the existing
base family; concrete resolved base and installed dependency versions belong in
build evidence, not an invented immutable claim. Build uses explicit Linux/amd64.
Numeric UID10008 serves private8000 and reads the declared wrapper path. No
credentials, controller package, runtime installation, host port or daemon mount.
Source gate owns its labelled build tag and cleanup; separately authorized
publication rebuilds and requires actual pulled-digest qualification afterward.
