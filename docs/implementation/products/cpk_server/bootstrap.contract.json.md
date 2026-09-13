Source: [bootstrap.contract.json](../../../../products/cpk_server/bootstrap.contract.json).
Maintain with source process inputs.

The source process now requires public trusted cpk-control-configuration.v1 JSON
at /etc/cpk/cpk-server/control.json, declared artifact cpk-control/0444/65,536-byte
maximum. Target/runtime and separate public verifier families are parent-produced;
no default private authority is provided. Main uses8080. Existing store and
operator bootstrap fields remain. This source contract does not retroactively
change the historical image's receiving ABI.
