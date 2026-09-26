Source: [bootstrap.contract.json](../../../../products/cpk_server/bootstrap.contract.json).
Maintain with source process inputs.

The source process now requires public trusted cpk-control-configuration.v1 JSON
at /etc/cpk/cpk-server/control.json, declared artifact cpk-control/0444/65,536-byte
maximum. Target/runtime and separate public verifier families are parent-produced;
no default private authority is provided. Main uses8080. Existing store and
operator bootstrap fields remain. This source contract does not retroactively
change the historical image's receiving ABI.

Issue235 declares optional CPK_MANAGED_HEALTH_SUPPORT_FILE as an operator-owned
absolute path. The separate closed source-support profile is bounded to1MiB/16
products and requires opened regular root/current-owned0444 input. Startup reads
one immutable snapshot before schema setup; absence is unsupported and invalid
present data fails startup. This public policy contains no private credential and
does not establish image/native-profile qualification. Actual file delivery uses
the existing selected ConfigurationArtifact and public environment mechanisms.
