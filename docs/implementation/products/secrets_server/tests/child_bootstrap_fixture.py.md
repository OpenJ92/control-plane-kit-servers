Source: [child_bootstrap_fixture.py](../../../../../products/secrets_server/tests/child_bootstrap_fixture.py).
Maintain with the focused Secrets smoke's verified reservation-owned volumes.

Creates the maintained synthetic seed only after all three opened volume roots
are empty. Directory FDs/no-follow and exclusive file creation prevent replacing
existing credentials/master material; unknown entries or a second initialization
are refused. File ownership/modes preserve the native product's protected-file
requirements. No secret is returned or printed. This helper does not initialize
the provider database, implement custody semantics or earn runtime acceptance.

Optional parent mode adds two synthetic Ed25519 key/token files and distinct
clients, each limited to write/resolve of one exact HTTP signer role in the
fixture workspace. All new private files are exclusive0400 and UID0 in the
existing protected client volume. Default child seed/grants stay unchanged.
