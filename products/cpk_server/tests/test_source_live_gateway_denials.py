from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load_source_live_module():
    spec = importlib.util.spec_from_file_location(
        "cpk_server_secret_provider_source_live_denials",
        SCRIPTS / "cpk_server_secret_provider_source_live.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("source-live controller module could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SourceLiveGatewayDenialTests(unittest.TestCase):
    def test_source_live_gateway_coordinate_is_immutable_and_in_memory_only(self) -> None:
        module = _load_source_live_module()
        coordinate = (
            "ghcr.io/openj92/control-plane-kit-servers/cpk-local-gateway@sha256:"
            + "a" * 64
        )
        with patch.dict(
            os.environ,
            {
                "CPK_SOURCE_LIVE_GATEWAY_IMAGE": coordinate,
                "CPK_SOURCE_LIVE_GATEWAY_SOURCE_COMMIT": "b" * 40,
            },
        ):
            document = module._source_live_gateway_document(ROOT)

        self.assertEqual(document.product.image.execution_reference, coordinate)
        self.assertEqual(
            dict(document.product.image.provenance or ())["source-commit"],
            "b" * 40,
        )
        self.assertNotIn(("a" * 64).encode("ascii"), (
            ROOT / "products" / "cpk_local_gateway" / "product.cpk.json"
        ).read_bytes())

    def test_source_live_gateway_coordinate_rejects_mutable_or_unknown_source(self) -> None:
        module = _load_source_live_module()
        cases = (
            ("ghcr.io/example/gateway:latest", "b" * 40),
            ("ghcr.io/example/gateway@sha256:" + "a" * 64, "branch-main"),
        )
        for coordinate, source_commit in cases:
            with self.subTest(coordinate=coordinate, source_commit=source_commit):
                with patch.dict(
                    os.environ,
                    {
                        "CPK_SOURCE_LIVE_GATEWAY_IMAGE": coordinate,
                        "CPK_SOURCE_LIVE_GATEWAY_SOURCE_COMMIT": source_commit,
                    },
                ):
                    with self.assertRaises(RuntimeError):
                        module._source_live_gateway_document(ROOT)

    def test_postgres_witness_calibrates_measurement_and_rejects_target_io(self) -> None:
        module = _load_source_live_module()
        snapshots = iter((10, 13, 16, 19, 24))
        witness = module.PostgresTransactionWitness.calibrate(
            lambda: next(snapshots)
        )

        witness.assert_no_target_io(lambda: None)
        with self.assertRaises(module.SourceLiveGatewayDenialError) as raised:
            witness.assert_no_target_io(lambda: None)

        self.assertEqual(raised.exception.code, "postgres-target-io-observed")
        self.assertEqual(repr(witness), "PostgresTransactionWitness(<bounded>)")

    def test_postgres_witness_fails_closed_when_measurement_is_unstable(self) -> None:
        module = _load_source_live_module()
        snapshots = iter((10, 13, 17))

        with self.assertRaises(module.SourceLiveGatewayDenialError) as raised:
            module.PostgresTransactionWitness.calibrate(lambda: next(snapshots))

        self.assertEqual(raised.exception.code, "postgres-witness-unstable")


if __name__ == "__main__":
    unittest.main()
