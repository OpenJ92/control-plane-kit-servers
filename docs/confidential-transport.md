# Confidential HTTP and MCP transport

The hosted operator HTTP boundary matches the route and authenticates once before
reading any body. Unknown routes return 404 and rejected credentials return 401
without reading it. Command bodies use the Core route's inclusive actual-byte
budget: ordinarily 65,536 bytes, and 98,304 bytes for secret-material provision.
Content-Length is not trusted. The first chunk exceeding the remaining allowance
is rejected before append, with fixed 413 `request body too large`; remaining
chunks are not drained by this collector.

GET routes reject their first nonempty body chunk with the existing 400 before
query validation. Commands reject nonempty query strings before reading bodies.
Empty GET bodies retain the declared query budgets and grammar. Existing neutral
byte APIs, route matching, framework 405 behavior and SDK routes keep their
contracts.

Hosted MCP has a separately approved inclusive 1,048,576-byte envelope budget.
Overflow returns fixed 413 before JSON parsing, authentication or dispatch. Below
that budget the order remains JSON parsing, MCP header validation, authentication
and operation dispatch. This total-envelope policy does not claim that every
previously unbounded JSON encoding fits. Existing per-command framing is unchanged.

MCP names resolve before arguments are retrieved. HTTP-only route IDs are refused
with fixed 404 even through HTTP-route fallback; they remain absent from canonical
MCP tools. Parsed JSON may already contain confidential-looking values in memory.
Service-request representations omit payloads, and unexpected service failures
return a fixed 500. Public bounded conflict/status references remain available.
Repr omission does not make arbitrary serialization safe. Bounded accumulation
does not promise zeroization, upstream ASGI allocation bounds or a timeout.

## Provision example for the later enabled composition

Provision remains unavailable through #316. #317 owns explicit enablement and
integration acceptance. This example documents that later HTTP surface; it was
not run against a live server or retained credentials.

Use an already authorized HTTPS endpoint and an existing registered provider.
The operator credential file must be protected (owner-only access) and contain
one complete `Authorization: Bearer ...` header. Do not paste its token into the
command, expand it into a shell variable used as an argument, or enable shell
tracing. The example reads that protected header file directly through curl.

Replace `your-approved-secret-source` with an approved tool that emits only the
material to stdout. Supply nonempty UTF-8 material of at most 65,536 bytes through
this pipe, including any intended newline bytes. The jq program builds base64
and JSON in memory; neither the material nor the request body is written to a
command file. All literal arguments below are public identifiers or paths.

```sh
set -o pipefail
your-approved-secret-source |
  jq --raw-input --slurp --compact-output \
    --arg request_id request-a \
    --arg provider_registration_id provider-a \
    --arg secret_reference secret://provider-a/cloudflare-token \
    --arg intent cloudflare.api-token \
    '{request_id: $request_id, provider_registration_id: $provider_registration_id,
      secret_reference: $secret_reference, intent: $intent, value_base64: (. | @base64)}' |
  curl --disable --silent --show-error --proto '=https' \
    --connect-timeout 10 --max-time 30 \
    --header @/protected/cpk-operator-header \
    --header 'Content-Type: application/json' \
    --data-binary @- --output /dev/null --write-out 'HTTP %{http_code}\n' \
    https://cpk.example.invalid/workspaces/workspace-a/secret-material/provision
```

The example does not follow redirects, retry, print the response body or disable
TLS verification. HTTP status alone is not durable acceptance evidence. A 409
or ambiguous transport failure must be inspected through the separately
authorized status read for the known workspace/request ID; do not blindly resend.
The safe GET path is
`/workspaces/workspace-a/secret-material-provisions/request-a`.
Operations owns permission checks, provider registration, receipts and history.
