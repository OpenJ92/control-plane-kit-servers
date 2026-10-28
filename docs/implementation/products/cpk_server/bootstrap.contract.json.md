Source: [bootstrap.contract.json](../../../../products/cpk_server/bootstrap.contract.json).
Maintain with source process inputs.

The source process now requires public trusted cpk-control-configuration.v1 JSON
at /etc/cpk/cpk-server/control.json, declared artifact cpk-control/0444/65,536-byte
maximum. Target/runtime and separate public verifier families are parent-produced;
no default private authority is provided. Main uses8080. Existing store and
operator bootstrap fields remain. This source contract does not retroactively
change the historical image's receiving ABI.

The optional managed-health mode declares `docker-unix-v1`, its explicit file
environment input, and public `cpk-server.managed-health.v1` JSON at the fixed
installation path. The file's 1 MiB maximum describes the standalone reader;
Core topology artifacts and complete product documents each have their separate
262,144-byte bounds. Mode absence preserves default startup. Enabled startup
requires Docker and provider material mode; scope references do not grant
authority. Source declarations do not claim an updated published-image ABI.

#345 declares dynamic-v1 workspace authority and docker-unix-v2 health. The latter
requires the matching private policy capability catalogue. The separate
installer_private_files declaration describes the fixed policy schema, numeric
recipient UID, 0400 mode, read-only subpath and installation lifetime. It is not
an ordinary public artifact slot; graph composition alone cannot satisfy it.
Source root apply remains explicitly incomplete before Docker until the remaining
initialization/enrollment children are integrated. The static v1 profile and
historical published-image coordinates remain distinct from this source contract.
