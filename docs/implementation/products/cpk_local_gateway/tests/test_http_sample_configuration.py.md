Source: products/cpk_local_gateway/tests/test_http_sample_configuration.py.

These tests cover public sample trust, explicit process selection and the real
gateway main's route composition using bounded file/uvicorn seams. The control
module is loaded in setUp, after product import-boundary tests remove gateway
modules from sys.modules. The fixture and patch therefore refer to the same live
module that main imports. A collection-time alias patched an obsolete object and
caused the existing CI test to read an absent configuration file and return2.
No production behavior, assertion, discovery or test isolation is weakened.
