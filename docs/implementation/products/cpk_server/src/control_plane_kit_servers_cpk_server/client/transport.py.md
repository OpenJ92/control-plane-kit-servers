#371 selects accepted Operations 9822cab5831c0cb7f8584a99607812b07cc346b6. Nonauthorization HTTP errors retain only an actual integer 4xx/5xx status. Only advancement reads an error body, capped at 8192+1 bytes, rejects duplicate/extra/malformed/unbound envelopes and validates the closed diagnostic with the accepted owner value. Every HTTPError body receives a close attempt, including authorization and invalid evidence. A close failure discards the diagnostic while preserving only safe actual status; successful closure is not claimed when close raises. Fixed failures are raised outside the handler to avoid retaining raw error context. Source review and the complete normal Docker gate passed at fdacc9405138e9b25b4c2928a3d5c13b9a7ecdae; required CI remains pending.

The gate passed all 1,260 product tests plus 26 test-support tests, compilation,
clean import and the normal smoke/cleanup stages. See [the complete result and
scoped cleanup limits](https://github.com/OpenJ92/control-plane-kit-servers/issues/371#issuecomment-6598347612).
Earlier pending-validation statements below describe historical slices.

The first consolidated gate at `5febb5f7` stopped at package integrity before
image build or product tests: the new close handler used a forbidden no-op
`except: pass`. The correction explicitly discards diagnostic evidence on close
failure while retaining only safe actual status. The bounded wire cohort covers
this case. No waiver or behavioral-green claim follows the first run; see
[the integrity stop](https://github.com/OpenJ92/control-plane-kit-servers/issues/371#issuecomment-6597592805).

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
