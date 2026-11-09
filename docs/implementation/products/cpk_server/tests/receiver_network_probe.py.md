Source: [receiver_network_probe.py](../../../../../products/cpk_server/tests/receiver_network_probe.py).
Maintain with the #163 retained-image diagnostic in the owning smoke.

This socket-free controller process reads only cpk-source:8080 on the owned
network. It uses bounded HTTP streaming and startup waiting, checks live/ready,
reuses the synthetic surface/health response verifier and authority refusals,
and requires the selected Operations authenticated missing-workspace404 plus
unauthorized401. Readiness alone does not establish SQL. A65-second alarm bounds
the helper. Only fixed stage/status/proof JSON is emitted even on failure; no
response body, header value or exception detail is emitted. The shell signals
the separate original all-checks signer when the probe has verified readiness,
even if a later source-control/workspace read fails. Both outcomes are retained
and either branch's failure fails the overall action.
