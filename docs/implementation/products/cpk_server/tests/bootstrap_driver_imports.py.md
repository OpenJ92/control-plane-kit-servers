Source: products/cpk_server/tests/bootstrap_driver_imports.py.

The shared import list names production modules and third-party runtime
dependencies required by the complete installer. Source validation checks those
modules before building; the finished image repeats imports and verifies its
installed distribution origins. PostgreSQL uses its actual configuration module.
