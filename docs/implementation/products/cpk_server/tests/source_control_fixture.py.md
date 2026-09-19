Source: [source_control_fixture.py](../../../../../products/cpk_server/tests/source_control_fixture.py).
Maintain with the source smoke's synthetic authority and cleanup plan.

The existing owning test image runs this fixed generate/verify process with
--network none, host UID/GID and one explicitly bound private fixture directory.
Generate creates a random synthetic workspace/revision/node/runtime, separate
in-memory Ed25519 pairs and240-second static/health grants. Only the actual public
ConfigurationArtifact (control.json0444) and two Authorization header files0600
are written, using exclusive/no-follow creation. Private keys never leave memory.
Grant generation occurs after image build and PostgreSQL preparation, immediately
before bounded source startup and protected reads. It does not retry/refresh a
failed authority or introduce an issuer service.

Verify reads each response at most65,537 bytes, checks exact static declaration
and uses actual NodeHealthReadResultCodec with the expected request/target/runtime
and declaration to require HEALTHY. Ordinary failure prints one fixed error with
no credential/response traceback. CLI never receives credentials as arguments.
The normal shell owns exact cleanup, including partial generation/request failure;
this helper owns no provider/runtime resources or ambient authority.
