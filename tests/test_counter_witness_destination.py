"""The actual pure shell boundary for the closed counter publication target."""
from pathlib import Path
import subprocess
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "counter_witness_destination.sh"


class CounterWitnessDestinationTests(unittest.TestCase):
    def destination(self, owner, package, tag):
        return subprocess.run(["sh", str(SCRIPT), owner, package, tag],
            capture_output=True, text=True, timeout=5, check=False)

    def test_counter_has_only_the_existing_private_storage_destination(self):
        for suffix in ("5d2de3c", "a" * 40):
            with self.subTest(suffix=suffix):
                tag = "counter-witness-264-" + suffix
                result = self.destination("openj92", "control-plane-kit-servers", tag)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout,
                    "ghcr.io/openj92/control-plane-kit-servers/cpk-server:" + tag + "\n")

    def test_overrides_production_tags_and_malformed_counter_tags_refuse(self):
        valid = "counter-witness-264-5d2de3c"
        cases = [("someone-else", "control-plane-kit-servers", valid),
            ("openj92", "somewhere-else", valid)]
        cases.extend(("openj92", "control-plane-kit-servers", tag) for tag in (
            "", "latest", "diagnostics-170-3ffc495", "counter-264-5d2de3c",
            "counter-witness-264-", "counter-witness-264-abcdef",
            "counter-witness-264-" + "a" * 41, "counter-witness-264-ABCDEF0",
            "counter-witness-264-abcdefg", valid + " ", valid + "\n",
            valid + "; echo unsafe", "$(echo unsafe)", '`echo unsafe`', '"; echo unsafe'))
        for arguments in cases:
            with self.subTest(arguments=arguments):
                result = self.destination(*arguments)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
