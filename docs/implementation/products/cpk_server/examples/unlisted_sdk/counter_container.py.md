Source: [counter_container.py](../../../../../../products/cpk_server/examples/unlisted_sdk/counter_container.py).

The private container entrypoint imports the existing Counter handler and real
SDK CpkHTTPServer, binds0.0.0.0:8000 and delegates configuration/declaration and
lifecycle health to SDK. It adds no route, identity, callback, signing or control
plane implementation. The loopback counter.py entrypoint remains unchanged.
The existing numeric-bootstrap witness supplies read-only public configuration;
the workload receives no daemon socket or private credentials. Startup under two
declarations is source evidence until independently qualified as an OCI artifact.
