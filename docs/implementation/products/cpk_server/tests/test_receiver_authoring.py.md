# `test_receiver_authoring.py`

The focused #238 tests build real Core deployment graphs and the local gateway's
real transit, wrapper, and route artifacts. They prove default-random fresh
identity sharing across Y's wrapper and G's route, exact retention of X and G
trust, omitted versus explicit-empty route semantics, exact pending lineage,
and fixed refusal for fresh gateways, current conflicts, and unresolved scopes.
They also cover variable-only verifier selection, legal uppercase/numeric Core
coordinates, opaque pending draft IDs, and exact context/request fence mismatch
refusal before key reads or identity generation.

The client tests prove `0600` artifact publication, authored journal profile,
byte-identical lost-response/restart replay, no callback or owner-read
regeneration, original-source drift refusal, and missing/corrupt artifact
refusal before a second dispatch. CLI tests preserve the closed group grammar.
The first-dispatch callback observes both the immutable artifact and pending
journal at the transport boundary, while injected preparation failure proves no
prepare dispatch occurs.
The import-isolation test also keeps the lightweight profile/bootstrap path
usable when the optional receiver-authoring Core surface is not installed.

Servers #245 strengthens complete authoring scenarios to retain self+X in A/C
and self+X+Y in B. The actual product self-health selector consumes every document;
it must return the retained gateway receiver. Separate registered source-product
scenarios compile real Gateway/Hello contracts and either another Hello or
Secrets. Core materialization supplies the exact same-runtime endpoint and each
product's declared port; Servers authoring copies those endpoints into explicit
route intents. Common own-health selection must agree with Y's authored target
and actual declaration. This is pure source composition using never-executed
image descriptors, not deployment, current graph advancement or saga evidence.
Omitted routes preserve bytes; the existing explicit-empty law remains tested.
