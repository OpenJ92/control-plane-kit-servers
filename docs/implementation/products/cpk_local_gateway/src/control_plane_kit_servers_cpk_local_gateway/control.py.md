# Gateway SDK and local truth

`install_gateway_control` revalidates actual public configuration, requires the
real configured relay and matching identity, constructs the actual selected SDK
verifiers/dispatcher, and installs its protected routes. Only successful
installation marks local composition configured. Authorization precedes the
product callbacks; there are no command/variable handlers or copied verifiers.

One application-owned `GatewayLocalHealth` holds configured/serving booleans.
Readiness is healthy only when both are true; the FastAPI lifespan sets serving
on entry and resets it in `finally`, including exceptional exit. Liveness means
the process can answer. These constant-time synchronous reads perform no target,
DNS, connector, secret, Docker or database work. A relay failure cannot change
local readiness. This is process state, not durable observation/lifecycle truth.

Minimal existing public status and protected correlated SDK health expose their
respective forms of this local fact. Public readiness is not authentication or
proof of the full management path. Interpreters148 owns concrete local observation
transport; connector188 owns connection truth;181/1860 own production authority
and history. No helper, exec fallback or additional socket recipient is introduced.
