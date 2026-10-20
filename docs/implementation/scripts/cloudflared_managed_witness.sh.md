# Managed cloudflared owning stage

Source: [cloudflared_managed_witness.sh](../../../scripts/cloudflared_managed_witness.sh).

Target-draft stage for Servers #284, invoked by normal `test.sh` after the
historical connector witness. It builds the distinct managed Dockerfile,
records the resulting image identity, and invokes the product target controller
using the existing package test image. The controller alone has the Docker
socket; product containers use network none and no host port bindings.

The run's unique ownership label is checked absent before creation. Cleanup
checks that label on each selected container and checks the recorded image
identity before deletion; it never prunes global state. The controller also
verifies exact created container identities. Trap cleanup preserves failure if
resource removal cannot be verified. Only named temporary fixture records are
removed after cleanup succeeds.
The final stage-success marker follows container, image and fixture cleanup.
The controller's earlier PASS is limited to its own observations and containers;
it cannot substitute for shell terminal success or the later global residue audit.

This stage has not been run. Managed Dockerfile/notice material is deliberately
not implemented before target review. A missing build file is an apparatus
failure, not meaningful red. Do not invoke it independently or create another
workflow. The existing entrypoint causal-red baseline remains the only run.
