Source: [scripts/cpk_server_workspace_a_router_transition_smoke.sh](../../../scripts/cpk_server_workspace_a_router_transition_smoke.sh).
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

This five-line entry point sets CPK_HOSTED_ACTIVITY_SCENARIO to
`workspace-a-router-transition` for one invocation of the
[hosted activity launcher](cpk_server_hosted_activity_smoke.sh.md). It assumes
the repository working directory and propagates that command's failure.

It adds no separate assertions, resource ownership, approval check or cleanup.
This is an ingress mode in the launcher and inherits its credential/provider
effects, legacy bootstrap incompatibilities and cleanup limits. The scenario
name is not evidence that its promised behavior ran.
