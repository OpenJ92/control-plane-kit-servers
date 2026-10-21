Source: [test_root_complete_setup.py](../../../../../products/cpk_server/tests/test_root_complete_setup.py).

Four laws run actual public_setup with its HTTP transport and socket-readiness
boundaries replaced by deterministic observations. Actual progress files are
written/read. They verify all four exact descriptor imports and canonical
references, preserve absent three-product behavior, and refuse a wrong fourth
reference or interrupted fourth import without falsely completing progress.
These are source owner tests, not live HTTP/image qualification.
