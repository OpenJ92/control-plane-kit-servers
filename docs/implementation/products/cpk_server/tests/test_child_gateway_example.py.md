Source: `products/cpk_server/tests/test_child_gateway_example.py`.
Maintain this document alongside its source file. When the source or relevant imported contracts change, verify and update this companion in the same change.

[Source](../../../../../products/cpk_server/tests/test_child_gateway_example.py) protects the [unmerged child recipe](../../../README.md): selected signer-document behavior, Hello/router/gateway topology and delegated ingress, finite custody/admission sequencing, plan comparison, and reconnect/cleanup evidence. It owns example composition laws, not Core event schemas or Operations state transitions.

The admission fake explicitly constructs the redacted public-key response shape and asserts that it contains no private-key reference; it does not instantiate an owning projection type. Command receipt fakes separately carry that reference. Product imports precede ingress/key admissions; a corrupt returned product reference stops after the first import. These assumptions address actual cross-owner mistakes and must survive fixture refactors. When the selected public projection changes, verify its owner rather than treating this literal fake as the source of that contract.

The Hello renderer is a contract oracle, and setup/teardown restores only newly imported Hello modules so later catalogue import-isolation tests remain meaningful. Do not “fix” ordering by weakening the catalogue law or keeping application imports globally cached.

Owners: [live_child_api.py](../../../../../products/cpk_server/tests/live_child_api.py), [public_child_api.py](../../../../../products/cpk_server/examples/public_child_api.py), and the selected Core/Operations projection contracts. This suite contains fakes and temporary files; green evidence does not prove the public deployment/restart/teardown ran. Source adoption and live disposition remain explicit in [#163](https://github.com/OpenJ92/control-plane-kit-servers/issues/163).
