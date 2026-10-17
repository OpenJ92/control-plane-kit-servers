Source: [test_hello_control.py](../../../../../products/hello_server/tests/test_hello_control.py).

Owning product tests use locally generated separate static/health Ed25519 keys,
nominal Core requests/grants and the actual SDK on Hello's stdlib host. They prove
configured artifact/source-contract roundtrips, closed input/file bounds,
opened-file regularity/symlink rejection, before-bind rejection, listener cleanup,
production port policy, valid signed reads, wrong-locality/family denials before
checks, fixed callback errors and per-instance settings/observations. The helper
hello_control_fixtures.py is test authority only, not a runnable product default.

Loopback hosts use finite test timeouts and join serving/request workers on close.
The tests do not duplicate SDK crypto/parser matrices, produce actual issuer
material, mount per-node artifacts or qualify an image/public deployment.

Receiving #237 target translation (before product implementation): own authority
is actual Core ReceiverNodeControlConfiguration with a full receiver target and
purpose-indexed verification families. Requests and real signed grants use
receiver V2 with a separate synthetic NodeControlAuthorityContext. No private
product configuration or compatibility alias is expected. The same installed
receiver must accept both request contexts; this is protocol evidence, not
Operations admission/current-authority or retained-process acceptance.

The source contract adds the single CPK_WRAPPER_CONFIGURATION_FILE binding.
Existing runtime ports, declarations and forwarding semantics are
preserved. Opened-file/symlink/FIFO/directory/byte-limit laws now enter the common
SDK loader through that binding, with exact 0444 mode required. Actual SDK
CpkThreadingHTTPServer owns passive setup, real serving state and teardown;
fixtures wait boundedly for its public cpk_is_serving property before requests.
Startup-failure tests observe the real unbound socket and retain closure checks
for actual SDK route-install, bind and activation failures. No private lifecycle
toggle or replacement receiver is used. Foreign workspace/runtime/node/socket/
receiver and original declaration/family denials preserve the callback/forwarding
boundary. All preexisting methods and effect assertions remain.

This target checkpoint has not run with the new closure. Initial gateway target
red proves only missing obsolete-profile refusal. Whole Servers and paired
Interpreter gates remain required; no host execution or alternate runner.

Current #241 coverage supersedes the earlier duplicate verification comparison:
the maintained source has empty native checks and keeps its SDK declaration;
the historical published descriptor still has native live/ready checks. Existing
real signed SDK cases retain healthy, unhealthy, callback-error and independent
instance/authority laws. Legacy HTTP-only assertions are removed; the second
instance now explicitly requires typed HEALTHY, not merely HTTP200. SDK owns
not-serving lifecycle semantics; the product still uses its real host wrapper.
