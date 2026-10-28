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
