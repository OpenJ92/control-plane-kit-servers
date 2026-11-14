# Fixed verification-only launcher

Binds the approved plan digest, clean source commit and reader/shared/launcher/
owner/daemon hashes before any credential mount. Checks reviewed input metadata,
baseline digest, selected local daemon and exact running original identity/port.
Starts one resource-bounded501 helper with no Docker socket/capabilities and no
switch entrypoint. Exact cid/status/ownership and helper cleanup are checked
before a closed result is retained. Existing evidence, uncertainty or any mismatch
stops without replay. Only owned helper resources may be removed; service resources
and prior switch evidence are retained. Offline validation uses the owning source
suite; live execution waits for North's relay of independent PASS.
