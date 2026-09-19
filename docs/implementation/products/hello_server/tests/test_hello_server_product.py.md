Source: [test_hello_server_product.py](../../../../../products/hello_server/tests/test_hello_server_product.py).

All 11 inherited product tests remain. The real HTML/legacy-route test now starts
the configured Hello host with generated test authority; its response assertions
are unchanged. The dependency source-shape check follows dependencies.py after
the product-local ownership split. Request receipt assertions now use an isolated
RequestObservations instance, preserving count/limit/query-redaction checks.
Published revision2 descriptor/capability/source/image behavior stays unchanged.
New signed composition and cooperative bounds are covered in the other owning
Hello tests; ordinary test.sh remains the only executable validation gate.
