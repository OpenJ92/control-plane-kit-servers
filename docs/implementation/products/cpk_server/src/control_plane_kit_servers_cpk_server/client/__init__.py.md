# `client/__init__.py`

The maintained public client package exports the closed receiver-authoring value
types alongside the existing topology client. It does not export persistence
internals or product wire-format helpers.

#280 adds `prepare_receiver_configuration` to the existing lazy public authoring
exports. Profile-only imports keep the same optional-dependency behavior. This
is the normal package entrance, not a version fallback or old-tuple compatibility
shim. The implementation and full owning gate are pending source acceptance.
