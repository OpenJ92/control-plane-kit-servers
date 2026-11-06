"""Source-built and immutable published Hello have distinct provenance owners."""
import json
from pathlib import Path
import unittest

from live_wrapper_artifacts import _require_hello_provenance


class WrapperArtifactProvenanceTests(unittest.TestCase):
    def setUp(self):
        upstreams = json.loads((Path(__file__).resolve().parents[3] /
            "coordinates/server-products.json").read_text())["upstreams"]
        self.source = {
            "control-plane-kit-core": "https://github.com/OpenJ92/control-plane-kit/archive/"
                + upstreams["control_plane_kit_core_commit"] + ".zip",
            "control-plane-kit-server-sdk": "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/"
                + upstreams["control_plane_kit_server_sdk_commit"] + ".zip",
        }
        self.published = {
            "control-plane-kit-core": "https://github.com/OpenJ92/control-plane-kit/archive/9861e536e79314005499ae07379f627bfb1599a2.zip",
            "control-plane-kit-server-sdk": "https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/d4e7c4d91c054f139e2971774ae5e37fc741262d.zip",
        }

    def test_each_mode_requires_its_own_tuple_and_rejects_cross_use(self):
        self.assertNotEqual(self.source, self.published)
        for mode, accepted, other in (
            ("source-built", self.source, self.published),
            ("published-digest", self.published, self.source),
        ):
            with self.subTest(mode=mode):
                _require_hello_provenance(accepted, mode=mode)
                with self.assertRaises(AssertionError):
                    _require_hello_provenance(other, mode=mode)

    def test_partial_extra_or_substituted_provenance_and_unknown_mode_refuse(self):
        for mode, expected in (("source-built", self.source), ("published-digest", self.published)):
            for candidate in ({}, {**expected, "extra": "unexpected"},
                    {**expected, "control-plane-kit-core": self.source["control-plane-kit-server-sdk"]}):
                with self.subTest(mode=mode, keys=tuple(candidate)):
                    with self.assertRaises(AssertionError):
                        _require_hello_provenance(candidate, mode=mode)
        with self.assertRaises(AssertionError):
            _require_hello_provenance(self.source, mode="unqualified")
