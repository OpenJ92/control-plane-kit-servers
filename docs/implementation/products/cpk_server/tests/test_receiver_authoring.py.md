# `test_receiver_authoring.py`

The focused #238 tests build real Core deployment graphs and the local gateway's
real transit, wrapper, and route artifacts. They prove default-random fresh
identity sharing across Y's wrapper and G's route, exact retention of X and G
trust, omitted versus explicit-empty route semantics, exact pending lineage,
and fixed refusal for fresh gateways, current conflicts, and unresolved scopes.

The client tests prove `0600` artifact publication, authored journal profile,
byte-identical lost-response/restart replay, no callback or owner-read
regeneration, original-source drift refusal, and missing/corrupt artifact
refusal before a second dispatch. CLI tests preserve the closed group grammar.
The import-isolation test also keeps the lightweight profile/bootstrap path
usable when the optional receiver-authoring Core surface is not installed.
