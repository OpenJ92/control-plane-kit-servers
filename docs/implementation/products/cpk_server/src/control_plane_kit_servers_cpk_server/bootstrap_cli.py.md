Source: [bootstrap_cli.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/bootstrap_cli.py).

#302 selects the verified plan's setup_products for the enabled complete profile;
otherwise public_setup uses the original installation.products.values() path.
The existing command sequence, exact ProductReference verification, durable
progress and bounded result projection are unchanged. Credential arguments are
absolute private-file Paths consumed by the real ClientProfile, not bearer text.
An interrupted fourth import leaves pending progress; a returned mismatched
reference cannot complete setup. This source change does not qualify serving
images, establish external readiness or add credentials/runtime access to the
website.
