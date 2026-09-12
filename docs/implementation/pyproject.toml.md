Source: [pyproject.toml](../../pyproject.toml).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This distribution includes the shared catalogue package and selected product implementation namespaces, and exposes the cpk CLI through the cpk-server client entrypoint. Package-data includes the generated catalogue and checksum. It does not start those product processes when the lightweight root is imported.

Core and Operations select the same exact source commit, while Interpreters selects its own exact commit plus cloudflare/docker/gateway/public-dns extras. The current consumer pins are Core/Operations e3e29995 and Interpreters e19da40; coordinate generation owns their synchronized replacements. Interpreters' direct Core URL selects the same e3e29995 archive, avoiding the former conflict between exact URLs. Third-party FastAPI/Uvicorn and build dependencies use ranges, so exact CPK pins do not make the whole environment a lockfile. Adoption requires checking the actual selected contracts, not importing newest upstream assumptions into documentation.

Related source and evidence: [coordinates/server-products.json](../../coordinates/server-products.json), [scripts/apply_coordinates.py](../../scripts/apply_coordinates.py), [src/control_plane_kit_servers/__init__.py](../../src/control_plane_kit_servers/__init__.py), [tests/test_package_metadata.py](../../tests/test_package_metadata.py).

Servers #177 consumes the reviewed CPK secret-delivery selection/admission correction through this generated pin. The installation composition test exercises the real composer and public Operations translator with default and substituted references. This packages future material behavior; it neither authorizes runtime effects nor changes persisted intents.
