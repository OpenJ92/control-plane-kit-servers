Source: [test_hello_server_product.py](../../../../../products/hello_server/tests/test_hello_server_product.py).

The real HTML/dependencies test starts the configured Hello host with generated
test authority. #241 removes its legacy-health route assertions while preserving
exact escaped HTML, headers and dependency output. The dependency source-shape check follows dependencies.py after
the product-local ownership split. Request receipt assertions now use an isolated
RequestObservations instance, preserving count/limit/query-redaction checks.
Published revision2 descriptor/capability/source/image behavior stays unchanged.
New signed composition and cooperative bounds are covered in the other owning
Hello tests; ordinary test.sh remains the only executable validation gate.

The #237 receiving migration uses the actual SDK CpkThreadingHTTPServer.
The invalid-color test spies on that constructor and retains its unchanged
palette/render assertions, exact fixed error and listener.assert_not_called.
Run 36938230303 exposed the stale ThreadingHTTPServer patch target before
main executed; changing the spy target preserves the law that invalid color
fails before any listener is constructed. No production guard or listener
behavior changes, and the unchanged whole gate owns executable validation.
