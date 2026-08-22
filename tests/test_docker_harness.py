import json
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_SMOKE = ROOT / "scripts" / "cpk_server_candidate_topology_smoke.sh"


class DockerHarnessTests(unittest.TestCase):
    def test_candidate_smoke_reuses_hosted_workflow_and_authoritative_residue_audit(
        self,
    ) -> None:
        self.assertTrue(
            CANDIDATE_SMOKE.is_file(),
            "candidate topology smoke wrapper is not implemented",
        )
        smoke = CANDIDATE_SMOKE.read_text(encoding="utf-8")

        self.assertIn("scripts/cpk_server_candidate_topology.py", smoke)
        self.assertNotIn("scripts/cpk_server_hosted_activity.py", smoke)
        self.assertIn("scripts/docker_residue_audit.sh", smoke)
        self.assertEqual(smoke.count("scripts/docker_residue_audit.sh"), 1)
        self.assertIn("candidate-assembly.json", smoke)
        self.assertIn("candidate-topology-report.json", smoke)
        for required in ("candidate-inspection.json", "--inspection"):
            with self.subTest(publication=required):
                self.assertIn(required, smoke)
        self.assertIn("CPK_SERVER_BASE_IMAGE", smoke)
        self.assertIn("sync_runtime_networks=False", smoke)
        self.assertNotIn("docker network connect", smoke)
        self.assertNotIn("sync_runtime_networks=True", smoke)
        self.assertNotIn("_sync_runtime_networks", smoke)
        self.assertNotIn("psql ", smoke)
        self.assertNotIn("SELECT ", smoke)
        self.assertNotIn("INSERT ", smoke)
        self.assertNotIn("UPDATE ", smoke)
        self.assertNotIn("DELETE FROM", smoke)
        self.assertNotIn("-X DELETE", smoke)
        self.assertNotIn('"DELETE"', smoke)
        self.assertNotIn("'DELETE'", smoke)
        self.assertNotIn("docker system prune", smoke)
        self.assertNotIn("docker volume prune", smoke)
        self.assertNotIn("docker compose", smoke)
        for required in (
            "pre_inventory",
            "post_inventory",
            "postgres_relations",
            "build_residue",
            "report_sha256",
        ):
            with self.subTest(observed_claim=required):
                self.assertIn(required, smoke)

    def test_candidate_smoke_cleanup_owns_abort_timeout_and_exact_labelled_residue(
        self,
    ) -> None:
        self.assertTrue(
            CANDIDATE_SMOKE.is_file(),
            "candidate topology smoke wrapper is not implemented",
        )
        smoke = CANDIDATE_SMOKE.read_text(encoding="utf-8")

        self.assertIn("trap cleanup EXIT HUP INT TERM", smoke)
        self.assertIn("org.openj92.project=control-plane-kit-servers", smoke)
        self.assertIn("org.openj92.cpk.scenario=candidate-topology-1714", smoke)
        self.assertIn("foreign_resource_canary", smoke)
        self.assertIn("first_failed_stage", smoke)
        for stale_cli_input in (
            "--foreign-canary",
            "--first-failed-stage",
            "--base-image",
        ):
            with self.subTest(stale_cli_input=stale_cli_input):
                self.assertNotIn(stale_cli_input, smoke)
        self.assertNotIn("--server-container", smoke)
        self.assertIn("timeout", smoke)
        self.assertIn("docker rm -f", smoke)
        self.assertIn("docker network rm", smoke)
        self.assertIn("docker image rm", smoke)
        self.assertIn("candidate-topology-report.json", smoke)
        for required in ('test -s "$REPORT"', "CPK_CANDIDATE_EVIDENCE_ID"):
            with self.subTest(publication=required):
                self.assertIn(required, smoke)
        self.assertNotIn("docker volume create", smoke)
        self.assertNotIn("DROP DATABASE", smoke)
        self.assertNotIn("DELETE FROM", smoke)
        self.assertNotIn("docker network connect", smoke)
        self.assertNotIn("sync_runtime_networks=True", smoke)
        self.assertNotIn("_sync_runtime_networks", smoke)
        self.assertNotIn("delete_workspace", smoke)
        self.assertNotIn("-X DELETE", smoke)
        self.assertNotIn('"DELETE"', smoke)
        self.assertNotIn("'DELETE'", smoke)
        self.assertNotIn("password", smoke.lower())
        for forbidden_name in (
            "cpk-1714-probe",
            "cpk-1714-candidate",
            "cpk-1714-runtime",
        ):
            with self.subTest(fixed_name=forbidden_name):
                self.assertNotIn(forbidden_name, smoke)

    def test_test_sh_is_docker_first_and_avoids_broad_cleanup(self) -> None:
        test_sh = (ROOT / "test.sh").read_text(encoding="utf-8")

        self.assertIn("docker build", test_sh)
        self.assertIn("docker run", test_sh)
        self.assertIn("scripts/docker_residue_audit.sh", test_sh)
        self.assertIn("scripts/apply_coordinates.py --check", test_sh)
        self.assertIn("/test-support/package_integrity.py", test_sh)
        self.assertIn("CPK_SERVER_BUILD_IMAGE=1", test_sh)
        self.assertIn('"$POLICY_IMAGE"', test_sh)
        self.assertIn("sh -c 'cd /test-support", test_sh)
        self.assertNotIn("docker system prune", test_sh)
        self.assertNotIn("docker volume prune", test_sh)

    def test_test_image_runs_unittest_and_product_image_lane(self) -> None:
        dockerfile = (ROOT / "Dockerfile.test").read_text(encoding="utf-8")
        runner = (ROOT / "scripts" / "run_all_tests.py").read_text(encoding="utf-8")

        self.assertIn("python:3.12-slim", dockerfile)
        self.assertIn("python", dockerfile)
        self.assertIn("scripts/run_all_tests.py", dockerfile)
        self.assertIn("COPY products ./products", dockerfile)
        self.assertIn("unittest", runner)
        self.assertIn("def product_test_roots", runner)
        self.assertIn('path / "tests"', runner)
        self.assertIn("product test package is missing", runner)
        self.assertIn("scripts/apply_coordinates.py", runner)
        self.assertIn("compileall", runner)
        self.assertIn("product_image_lane.py", runner)

    def test_product_image_lane_reports_cpk_server_image_definition(self) -> None:
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
        self.assertEqual(
            [product["product_id"] for product in report["products"]],
            [
                "cpk-server",
                "cpk-server-docker",
                "cpk-server-docker-cloudflare",
                "hello-server",
                "http-active-router",
                "http-multiplexer",
                "cpk-local-gateway",
                "cloudflared-connector",
                "postgres-server",
                "secrets-server",
            ],
        )
        self.assertEqual(
            report["image_builds"],
            [
                {
                    "product_id": "cpk-server",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/cpk_server/Dockerfile",
                    "status": "image-definition-present",
                },
                {
                    "product_id": "cpk-server-docker",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/cpk_server/Dockerfile",
                    "status": "image-definition-present",
                },
                {
                    "product_id": "cpk-server-docker-cloudflare",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/cpk_server/Dockerfile",
                    "status": "image-definition-present",
                },
                {
                    "product_id": "hello-server",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/hello_server/Dockerfile",
                    "status": "image-definition-present",
                },
                {
                    "product_id": "http-active-router",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/http_active_router/Dockerfile",
                    "status": "image-definition-present",
                },
                {
                    "product_id": "http-multiplexer",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/http_multiplexer/Dockerfile",
                    "status": "image-definition-present",
                },
                {
                    "product_id": "cpk-local-gateway",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/cpk_local_gateway/Dockerfile",
                    "status": "image-definition-present",
                },
                {
                    "product_id": "cloudflared-connector",
                    "image_source": "external-oci",
                    "external_image": "docker.io/cloudflare/cloudflared@sha256:6d91c121b803126f7a5344005d17a9324788fc09d305b6e2560ec6040a7ae283",
                    "status": "external-oci-pinned",
                },
                {
                    "product_id": "postgres-server",
                    "image_source": "external-oci",
                    "external_image": "docker.io/library/postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777",
                    "status": "external-oci-pinned",
                },
                {
                    "product_id": "secrets-server",
                    "image_source": "local-dockerfile",
                    "dockerfile": "products/secrets_server/Dockerfile",
                    "status": "image-definition-present",
                },
            ],
        )
        self.assertEqual(report["status"], "product-image-definitions-present")


    def test_publish_product_image_workflow_is_per_product_and_uses_ghcr(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "publish-product-image.yml").read_text(
            encoding="utf-8"
        )
        script = (ROOT / "scripts" / "publish_product_image.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("workflow_dispatch", workflow)
        self.assertIn("packages: write", workflow)
        self.assertIn("scripts/publish_product_image.sh", workflow)
        self.assertIn("ghcr.io", script)
        self.assertIn("products/cpk_server/Dockerfile", script)
        self.assertIn("products/hello_server/Dockerfile", script)
        self.assertIn("products/http_active_router/Dockerfile", script)
        self.assertIn("products/http_multiplexer/Dockerfile", script)
        self.assertIn("products/cpk_local_gateway/Dockerfile", script)
        self.assertIn("products/secrets_server/Dockerfile", script)
        self.assertIn("unsupported product id", script)
        self.assertNotIn("docker system prune", script)
        self.assertNotIn("docker volume prune", script)

    def test_residue_audit_filters_only_owned_resources(self) -> None:
        audit = (ROOT / "scripts" / "docker_residue_audit.sh").read_text(encoding="utf-8")

        self.assertIn("org.openj92.project=control-plane-kit-servers", audit)
        self.assertIn("docker ps", audit)
        self.assertIn("docker network ls", audit)
        self.assertIn("docker volume ls", audit)
        self.assertNotIn("docker rm", audit)
        self.assertNotIn("docker volume rm", audit)
        self.assertNotIn("prune", audit)
        self.assertIn("Pottery Factory", audit)

    def test_github_actions_run_authoritative_gate_for_every_pull_request(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("main", workflow)
        self.assertIn("develop", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn("pull_request:\n    branches:", workflow)
        self.assertIn("./test.sh", workflow)


if __name__ == "__main__":
    unittest.main()
