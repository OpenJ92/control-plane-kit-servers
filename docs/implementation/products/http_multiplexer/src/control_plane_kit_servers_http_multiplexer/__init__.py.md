Source: [products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/__init__.py](../../../../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/__init__.py).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This facade exposes MultiplexerSettings, MultiplexerConfigurationError and main
from the process module. Import loads definitions without invoking main or
binding HTTP. Product descriptor decoding and instantiation do not depend on
this facade and do not start the workload.

Related source and evidence: [products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py](../../../../../../products/http_multiplexer/src/control_plane_kit_servers_http_multiplexer/server.py), [products/http_multiplexer/tests/test_http_multiplexer_product.py](../../../../../../products/http_multiplexer/tests/test_http_multiplexer_product.py).
