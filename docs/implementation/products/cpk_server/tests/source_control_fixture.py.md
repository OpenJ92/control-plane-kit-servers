Source: [source_control_fixture.py](../../../../../products/cpk_server/tests/source_control_fixture.py).
Maintain with the source smoke's synthetic authority and cleanup plan.

The existing owning test image runs this fixed generate/verify process with
--network none, host UID/GID and one explicitly bound private fixture directory.
Generate creates a random synthetic workspace/node/runtime/receiver, separate
in-memory Ed25519 pairs and240-second static/health grants. Only the actual public
ConfigurationArtifact (control.json0444) and two Authorization header files0600
are written, using exclusive/no-follow creation. Private keys never leave memory.
Grant generation occurs after image build and PostgreSQL preparation, immediately
before bounded source startup and protected reads. It does not retry/refresh a
failed authority or introduce an issuer service.

Verify reads each response at most65,537 bytes, checks exact static declaration
and uses actual ReceiverHealthReadResultCodec with the expected request/target/context
and declaration to require HEALTHY. Ordinary failure prints one fixed error with
no credential/response traceback. CLI never receives credentials as arguments.
The normal shell owns exact cleanup, including partial generation/request failure;
this helper owns no provider/runtime resources or ambient authority.

#237 changes the generated artifact and grants to common receiver configuration
and receiver-health/surface profiles. Verification uses ReceiverHealthReadResultCodec
with an explicit test-owned AUTHORITY constant, also supplied at signing time;
it never derives current authority from installed receiver identity. The three
output files, modes, bounded lifetime, no-follow/exclusive creation and cleanup ABI
are unchanged. No source smoke was run for the target translation.
