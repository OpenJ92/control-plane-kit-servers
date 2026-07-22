import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DockerHarnessTests(unittest.TestCase):
    def test_test_sh_is_docker_first_and_avoids_broad_cleanup(self) -> None:
        test_sh = (ROOT / "test.sh").read_text(encoding="utf-8")

        self.assertIn("docker build", test_sh)
        self.assertIn("docker run", test_sh)
        self.assertIn("scripts/docker_residue_audit.sh", test_sh)
        self.assertNotIn("python -m unittest", test_sh)
        self.assertNotIn("docker system prune", test_sh)
        self.assertNotIn("docker volume prune", test_sh)

    def test_test_image_runs_unittest_and_product_image_lane(self) -> None:
        dockerfile = (ROOT / "Dockerfile.test").read_text(encoding="utf-8")
        runner = (ROOT / "scripts" / "run_all_tests.py").read_text(encoding="utf-8")

        self.assertIn("python:3.12-slim", dockerfile)
        self.assertIn("python", dockerfile)
        self.assertIn("scripts/run_all_tests.py", dockerfile)
        self.assertIn("unittest", runner)
        self.assertIn("product_image_lane.py", runner)

    def test_product_image_lane_reports_empty_inventory_without_building(self) -> None:
        result = subprocess.run(
            [
                "python",
                str(ROOT / "scripts" / "product_image_lane.py"),
                "--inventory",
                str(ROOT / "coordination" / "product-inventory.json"),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        report = json.loads(result.stdout)

        self.assertEqual(report["schema"], "cpk-servers.product-image-lane-report")
        self.assertEqual(report["products"], [])
        self.assertEqual(report["image_builds"], [])
        self.assertEqual(report["status"], "no-products")

    def test_residue_audit_filters_only_owned_resources(self) -> None:
        audit = (ROOT / "scripts" / "docker_residue_audit.sh").read_text(encoding="utf-8")

        self.assertIn("org.openj92.project=control-plane-kit-servers", audit)
        self.assertIn("docker ps", audit)
        self.assertIn("docker volume ls", audit)
        self.assertNotIn("docker rm", audit)
        self.assertNotIn("docker volume rm", audit)
        self.assertNotIn("prune", audit)
        self.assertIn("Pottery Factory", audit)

    def test_github_actions_run_tests_on_main_and_develop(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("main", workflow)
        self.assertIn("develop", workflow)
        self.assertIn("./test.sh", workflow)


if __name__ == "__main__":
    unittest.main()
