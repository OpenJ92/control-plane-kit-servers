# Servers readiness implementation companions

Use the [shared #1799 convention](https://github.com/OpenJ92/control-plane-kit/issues/1799): `docs/implementation/<source-path>.md`, source/update reminder first, source and selected-import verification, and same-change companion maintenance through the existing PR log. Short law/owner notes are complete when they identify the file's actual role; generic stubs are not.

[Inventory](inventory.json) tracks the stable readiness scope governed by [Servers #172](https://github.com/OpenJ92/control-plane-kit-servers/issues/172). Source coordinates and review depth live in its issue/PR evidence. Coverage states are rollout accounting, separate from unresolved defects and runtime acceptance.

The unmerged child-acceptance harness is a separate [#173 adoption slice](https://github.com/OpenJ92/control-plane-kit-servers/issues/173), authored against its actual child source. It is not part of this baseline merely because a documentation draft exists. On source adoption, review overlapping bootstrap/gate/test companions, remove companions for removed source, and retarget the draft after resolving overlap. The held live run remains uncertain; these notes authorize no diagnostics or deployment.

Three different catalogues must stay distinct: this package's publication metadata, Core's decoded product values, and the maintained client's desired-topology draft catalogue. Reading a local published product document is not a public product registration. A consumer needing registration must use its explicit public import/setup contract before planning.
