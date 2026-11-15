import json
from pathlib import Path
import tempfile
import unittest

from scripts.test_cohort import admit, EXPECTED, AUTHORING_EXPECTED


class CohortManifestTests(unittest.TestCase):
    def test_authoring_is_an_independent_exact_selection_without_pin_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            path.write_text(json.dumps(AUTHORING_EXPECTED))
            self.assertEqual(admit(path, cohort="topology-authoring"), AUTHORING_EXPECTED)
            with self.assertRaises(ValueError):
                admit(path)
            for value in ({**AUTHORING_EXPECTED, "core": EXPECTED["core"]},
                    {**AUTHORING_EXPECTED, "operations": EXPECTED["operations"]},
                    {**AUTHORING_EXPECTED, "sdk": "0" * 40},
                    {**AUTHORING_EXPECTED, "extra": "ignored"}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    admit(path, cohort="topology-authoring")
            path.write_text(json.dumps(EXPECTED))
            self.assertEqual(admit(path), EXPECTED)
            with self.assertRaises(ValueError):
                admit(path, cohort="topology-authoring")
            with self.assertRaises(ValueError):
                admit(path, cohort="unreviewed")

    def test_only_reviewed_complete_cohort_is_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            path.write_text(json.dumps(EXPECTED))
            self.assertEqual(admit(path), EXPECTED)
            for value in ({**EXPECTED, "sdk": "0" * 40}, {**EXPECTED, "servers": "a" * 40},
                          {**EXPECTED, "extra": "ignored"}, {key: val for key, val in EXPECTED.items() if key != "sdk"}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    admit(path)

    def test_duplicate_fields_refuse_instead_of_selecting_last(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            path.write_text(json.dumps(EXPECTED)[:-1] + ', "sdk": "' + EXPECTED["sdk"] + '"}')
            with self.assertRaises(ValueError):
                admit(path)
