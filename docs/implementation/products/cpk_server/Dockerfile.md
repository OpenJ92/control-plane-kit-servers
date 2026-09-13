Source: [products/cpk_server/Dockerfile](../../../../products/cpk_server/Dockerfile).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This is the shared process-image build lane for all three CPK descriptors.
It installs the coordinate-selected Core and Operations source commit and the
Interpreters commit with Cloudflare, Docker, gateway and public-DNS extras.
Available interpreter software is distinct from the selected process mode and
from workspace authority. The recipe contains no provider credentials or
Docker socket mount.

The Python base is tagged and FastAPI/Uvicorn use lower bounds, so source pins
do not make the entire build immutable. Product source is copied from the
checkout, owned by the cpk account, and run under numeric UID 10001. The default
command starts the server module; EXPOSE 8080 does not publish a host port.
Database, auth and interpreter bootstrap inputs are supplied at runtime.

Review dependency changes against the actual selected commits, not current
upstream heads. Building this recipe does not establish the published digest
or verify its account/HOME/protected-file behavior; those are separate image
identity and numeric-recipient witnesses.

Related source and evidence: [coordinates/server-products.json](../../../../coordinates/server-products.json), [products/cpk_server/bootstrap.contract.json](../../../../products/cpk_server/bootstrap.contract.json), [products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py](../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/server.py), [products/cpk_server/tests/live_numeric_bootstrap.py](../../../../products/cpk_server/tests/live_numeric_bootstrap.py), [products/cpk_server/tests/test_image_bootstrap.py](../../../../products/cpk_server/tests/test_image_bootstrap.py).

The Core/Operations mirror selects reviewed CPK merge `95452249d0340707a5cdffe737e34669e9d53165` through Servers #193's canonical coordinate generator. Existing secret-delivery corrections remain available and optional health contracts are added upstream; Operations source is unchanged in the adopted interval. The published image coordinate remains separate and unchanged.

The Interpreters mirror selects reviewed merge `77c9a7f54e6d8ef886733c8ebd3476e796fad8ad`. Its direct Core dependency uses the same exact archive as this recipe and the root SDK dependency. This recipe does not install SDK yet; CPK's own wrapper issue owns that addition. Ordinary source-image witnesses establish current composition, not new SDK capability or publication.
