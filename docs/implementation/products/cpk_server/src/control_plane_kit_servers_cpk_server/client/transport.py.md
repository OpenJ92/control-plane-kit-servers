#371 selects accepted Operations 9822cab5831c0cb7f8584a99607812b07cc346b6. Nonauthorization HTTP errors retain only an actual integer 4xx/5xx status. Only advancement reads an error body, capped at 8192+1 bytes, rejects duplicate/extra/malformed/unbound envelopes and validates the closed diagnostic with the accepted owner value. Every HTTPError body closes, including authorization and invalid evidence. Fixed failures are raised outside the handler to avoid retaining raw error context. Source review and consolidated normal Docker validation are pending.

# Public HTTP client transport

GET query encoding follows the existing shared boundary contract: runtime_id and
authority_ref are raw text, limit is a positive integer (not bool), and target/
after are JSON objects. Other existing GET fields, including receiver-authoring
expected/pending_draft, retain JSON encoding. Percent encoding preserves spaces
and literal plus. The final encoded byte count uses the route's request bound.

Malformed, nonfinite, unserializable and oversized query values refuse before
credential lookup or outbound I/O. The fixed error is raised after the exception
handler to avoid retaining payload-bearing serialization context. Authentication,
route selection, response bounds and POST behavior retain their existing owners.
The #341 combined target run40643526308 reached the missing query behavior;
implementation green remains pending. Boundary routing tests are not durable
permission or pagination evidence.
