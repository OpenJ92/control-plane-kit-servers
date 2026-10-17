Source: [__init__.py](../../../../../../products/http_active_router/src/control_plane_kit_servers_http_active_router/__init__.py).
Maintain with the package entrance.

RouterSettings and RouterConfigurationError come from local configuration values.
The existing package-level main callable lazily imports process composition only
when called. Merely importing values does not load the HTTP process, bind a socket
or read startup environment/configuration. Existing server-level settings imports
continue to resolve the same local nominal type.
