# Tests workflow and retained connector mode

Ordinary push, PR and manual invocations retain the existing Docker suite and
root/wrapper input selection. The default-false retained_managed_connector input
selects a mutually exclusive job only for workflow_dispatch. That job rejects
simultaneous root/wrapper requests before checkout/login/effects, then composes
the reviewed orchestration with the fixed historical cc1 owner. The existing
contents:read/packages:read permissions are unchanged.

The fixed mode's concurrency group is separate and does not cancel in-progress
qualification; ordinary runs retain their original group and cancellation
behavior. No triggers were added. This uses the already registered workflow at a
reviewed execution ref rather than requiring a new workflow on the default
branch. Only bounded result.json is uploaded for 30 days. No dispatch has been
performed as part of source validation.
