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

## Provision example for configured custody and authority

Provision requires the configured provider custodian and explicit independent
principal authority described in [deployment input authority](deployment-input-authority.md).
Missing dependencies remain unavailable. #317 source enablement is pending normal
green/integrated acceptance. This example has not been run against a live server
or retained credentials.

Use an already authorized HTTPS endpoint and an existing registered provider.
The operator credential file must be protected (owner-only access) and contain
one complete `Authorization: Bearer ...` header. Do not paste its token into the
command, expand it into a shell variable used as an argument, or enable shell
tracing. The example reads that protected header file directly through curl.

Replace `your-approved-secret-source` with an approved tool that emits only the
material to stdout. Its arguments must contain no credentials or material. Save
the following non-confidential source as a script and run it only for the later
authorized enabled composition. The producer must finish successfully before
curl starts; a nonzero exit after partial output sends no request. The script
retains at most 65,537 producer bytes, rejects empty/oversized/non-UTF-8 material,
and preserves intended newline bytes. Base64 and JSON stay in memory and enter
curl through stdin. The protected operator header file is read directly by curl.

```python
import base64
import json
import subprocess

with subprocess.Popen(
    ["your-approved-secret-source"],
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
) as source:
    material = source.stdout.read(65_537)
    if len(material) > 65_536:
        source.kill()
        source.wait()
        raise SystemExit("material exceeds the byte limit; no request sent")
    if source.wait() != 0:
        raise SystemExit("material producer failed; no request sent")

if not material:
    raise SystemExit("material is empty; no request sent")
try:
    material.decode("utf-8")
except UnicodeDecodeError:
    raise SystemExit("material must be UTF-8; no request sent") from None

body = json.dumps({
    "request_id": "request-a",
    "provider_registration_id": "provider-a",
    "secret_reference": "secret://provider-a/cloudflare-token",
    "intent": "cloudflare.api-token",
    "value_base64": base64.b64encode(material).decode("ascii"),
}).encode("utf-8")
if len(body) > 98_304:
    raise SystemExit("request exceeds the byte limit; no request sent")

result = subprocess.run([
    "curl", "--disable", "--silent", "--show-error", "--proto", "=https",
    "--connect-timeout", "10", "--max-time", "30",
    "--header", "@/protected/cpk-operator-header",
    "--header", "Content-Type: application/json",
    "--data-binary", "@-", "--output", "/dev/null",
    "--write-out", "HTTP %{http_code}\\n",
    "https://cpk.example.invalid/workspaces/workspace-a/secret-material/provision",
], input=body, check=False)
raise SystemExit(result.returncode)
```

The example does not follow redirects, retry, print the response body or disable
TLS verification. HTTP status alone is not durable acceptance evidence. A 409
or ambiguous transport failure must be inspected through the separately
authorized status read for the known workspace/request ID; do not blindly resend.
The safe GET path is
`/workspaces/workspace-a/secret-material-provisions/request-a`.
Operations owns permission checks, provider registration, receipts and history.
