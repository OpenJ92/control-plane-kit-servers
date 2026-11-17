import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.test_cohort import admit, EXPECTED, AUTHORING_EXPECTED


class CohortManifestTests(unittest.TestCase):
    def test_export_coordinates_match_each_admitted_manifest(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "test_cohort.py"
        for cohort in (EXPECTED, AUTHORING_EXPECTED):
            pins = [cohort[role] for role in ("core", "operations", "interpreters", "sdk")]
            archive = cohort["interpreters_source"]
            export = [*pins, archive["sha256"], archive["module_tree"]]
            for action, expected in (("admit", pins), ("admit-export", export)):
                with self.subTest(cohort=cohort["name"], action=action):
                    output = subprocess.check_output([sys.executable, script, action, cohort["name"]], text=True)
                    self.assertEqual(output.split(), expected)

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

    def test_cohorts_reject_crossed_interpreter_provenance_and_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            for selected, other in ((EXPECTED, AUTHORING_EXPECTED), (AUTHORING_EXPECTED, EXPECTED)):
                for field in ("interpreters", "sdk", "sha256", "module_tree"):
                    with self.subTest(cohort=selected["name"], field=field):
                        candidate = dict(selected)
                        if field in ("sha256", "module_tree"):
                            candidate["interpreters_source"] = {
                                **selected["interpreters_source"], field: other["interpreters_source"][field]}
                        else:
                            candidate[field] = other[field]
                        path.write_text(json.dumps(candidate))
                        with self.assertRaises(ValueError):
                            admit(path, cohort=selected["name"])

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
