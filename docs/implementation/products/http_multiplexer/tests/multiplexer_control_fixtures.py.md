Source: [multiplexer_control_fixtures.py](../../../../../products/http_multiplexer/tests/multiplexer_control_fixtures.py).
Maintain with synthetic product authority and host ownership.

Fixtures generate independent Ed25519 static/health keys in memory and sign actual
Core grants for a fixed injected clock. No deployable private/default key is saved.
The actual factory runs on loopback port0; tests bound client reads/timeouts and
close clients, host socket and worker threads, joining from outside serve_forever.
Application body/headers can be supplied to prove real handler composition. These
helpers run through the existing owning suite, not a new gate or runtime framework.

Receiving #237 target translation (before product implementation): own authority
is actual Core ReceiverNodeControlConfiguration with a full receiver target and
purpose-indexed verification families. Requests and real signed grants use
receiver V2 with a separate synthetic NodeControlAuthorityContext. No private
product configuration or compatibility alias is expected. The same installed
receiver must accept both request contexts; this is protocol evidence, not
Operations admission/current-authority or retained-process acceptance.

The source contract adds the single CPK_WRAPPER_CONFIGURATION_FILE binding.
Existing runtime ports, declarations, verification and forwarding semantics are
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
