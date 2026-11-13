Source: [delegation_key_generation.py](../../../../../../products/cpk_server/src/control_plane_kit_servers_cpk_server/delegation_key_generation.py).

#315's private adapter joins an admitted Operations generation grant to the
existing public Secrets client. Construction validates registry/policy types
without registry resolution or credential IO. generate selects the grant's exact
endpoint and credential references through configuration_for, constructs one
public client with the shared transport/policy and maps workspace, reference,
purpose, issuer, actor subject and correlation. Its validated result is returned
unchanged and exceptions propagate without retry. No private custodian helpers,
key material handling, durable writes, admission or uncertainty logic live here.
The configured client and Operations own their existing transport and attempt
semantics. The adapter representation exposes no registry, endpoint or material.
