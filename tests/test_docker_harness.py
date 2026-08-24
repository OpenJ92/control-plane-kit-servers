import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_SMOKE = ROOT / "scripts" / "cpk_server_candidate_topology_smoke.sh"
CANDIDATE_RUNNER = ROOT / "scripts" / "cpk_server_candidate_topology.py"


class DockerHarnessTests(unittest.TestCase):
    def test_candidate_runner_bounds_readiness_and_admits_socket_before_mutation(
        self,
    ) -> None:
        runner = CANDIDATE_RUNNER.read_text(encoding="utf-8")

        with self.subTest(boundary="bounded-postgres-readiness"):
            for required in (
                "POSTGRES_READY_ATTEMPTS",
                "POSTGRES_READY_RETRY_SECONDS",
                "pg_isready",
                "_sleep",
            ):
                self.assertIn(required, runner)
            self.assertNotIn("while True", runner)
        with self.subTest(boundary="owned-server-environment"):
            for required in (
                "CPK_WORKPLACE_DATABASE_URL",
                "CPK_ACTIVITY_HISTORY_DATABASE_URL",
                "CPK_OBSERVER_STATE_DATABASE_URL",
                "CPK_GRAPH_TOPOLOGY_DATABASE_URL",
                'self._name("postgres")',
                '"credential": "present"',
                '"credential": "worker-present"',
            ):
                self.assertIn(required, runner)
            self.assertNotIn("name: os.environ[name]", runner)
            self.assertNotIn("if name in os.environ", runner)
        with self.subTest(boundary="socket-before-docker-mutation"):
            self.assertIn("stat.S_ISSOCK", runner)
            self.assertNotIn("docker_socket_gid = 0", runner)
            socket_position = runner.find("os.stat(DOCKER_SOCKET)")
            network_position = runner.find("self._client.networks.create")
            container_position = runner.find("self._client.containers.run")
            self.assertGreaterEqual(socket_position, 0)
            self.assertGreaterEqual(network_position, 0)
            self.assertGreaterEqual(container_position, 0)
            if min(socket_position, network_position, container_position) >= 0:
                self.assertLess(socket_position, network_position)
                self.assertLess(socket_position, container_position)
        with self.subTest(boundary="provider-image-provenance"):
            self.assertIn("RepoDigests", runner)
            self.assertIn('"Config"', runner)
            self.assertIn('"Image"', runner)
            self.assertIn("target_image_reference", runner)

    def test_candidate_smoke_measures_dynamic_sources_artifacts_and_base_image_before_mutation(
        self,
    ) -> None:
        smoke = CANDIDATE_SMOKE.read_text(encoding="utf-8")
        runner_call = "python -m scripts.cpk_server_candidate_topology"

        with self.subTest(boundary="runner-source-coordinate"):
            self.assertIn('git -C "$ROOT" rev-parse HEAD', smoke)
            self.assertIn('git -C "$ROOT" rev-parse HEAD^{tree}', smoke)
            self.assertIn('git -C "$ROOT" diff --quiet', smoke)
            self.assertIn('git -C "$ROOT" diff --cached --quiet', smoke)
        with self.subTest(boundary="candidate-source-coordinate"):
            self.assertIn("CPK_CANDIDATE_ROOT", smoke)
            self.assertIn('git -C "$CPK_CANDIDATE_ROOT" rev-parse HEAD', smoke)
            self.assertIn('git -C "$CPK_CANDIDATE_ROOT" rev-parse HEAD^{tree}', smoke)
            self.assertIn('git -C "$CPK_CANDIDATE_ROOT" diff --quiet', smoke)
            self.assertIn('git -C "$CPK_CANDIDATE_ROOT" diff --cached --quiet', smoke)
        with self.subTest(boundary="measured-build-inputs"):
            self.assertIn("products/cpk_server/Dockerfile", smoke)
            self.assertIn("acceptance/candidate_topology/Dockerfile", smoke)
            self.assertIn("dist/control_plane_kit_core.whl", smoke)
            self.assertIn("dist/control_plane_kit_operations.whl", smoke)
            self.assertIn("dist/rfc8785-0.1.4-py3-none-any.whl", smoke)
            self.assertIn(
                "520d690b448ecf0703691c76e1a34a24ddcd4fc5bc41d589cb7c58ec651bcd48",
                smoke,
            )
            self.assertGreaterEqual(smoke.count("sha256"), 5)
        with self.subTest(boundary="immutable-base-image-measurement"):
            self.assertIn("docker image inspect", smoke)
            self.assertIn("CPK_SERVER_BASE_IMAGE", smoke)
            self.assertIn("{{.Id}}", smoke)
        with self.subTest(boundary="runner-module-invocation"):
            self.assertIn('cd "$ROOT"', smoke)
            self.assertEqual(smoke.count(runner_call), 1)
        with self.subTest(boundary="reject-direct-root-runner"):
            self.assertNotIn(
                'python "$ROOT/scripts/cpk_server_candidate_topology.py"',
                smoke,
            )
        with self.subTest(boundary="measurement-precedes-runner-mutation"):
            positions = tuple(
                smoke.find(token)
                for token in (
                    "rev-parse HEAD",
                    "sha256",
                    "docker image inspect",
                    runner_call,
                )
            )
            all_present = all(position >= 0 for position in positions)
            self.assertTrue(
                all_present,
                "candidate measurement ordering token is missing",
            )
            if all_present:
                for measurement_position in positions[:-1]:
                    self.assertLess(measurement_position, positions[-1])

    def test_candidate_smoke_reuses_hosted_workflow_and_authoritative_residue_audit(
        self,
    ) -> None:
        self.assertTrue(
            CANDIDATE_SMOKE.is_file(),
            "candidate topology smoke wrapper is not implemented",
        )
        smoke = CANDIDATE_SMOKE.read_text(encoding="utf-8")
        runner = CANDIDATE_RUNNER.read_text(encoding="utf-8")

        self.assertIn("python -m scripts.cpk_server_candidate_topology", smoke)
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
            "report_sha256",
        ):
            with self.subTest(observed_claim=required):
                self.assertIn(required, smoke)
        for surface_name, surface in (("runner", runner), ("smoke", smoke)):
            with self.subTest(
                obsolete_public_claim="provider-internal-build-residue",
                surface=surface_name,
            ):
                self.assertNotIn("build_residue", surface)
            with self.subTest(
                obsolete_public_claim="cleanup-completion-status",
                surface=surface_name,
            ):
                self.assertNotIn("cleanup_terminal", surface)

    def test_candidate_smoke_ledger_owns_interruption_and_exact_cleanup(
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
        self.assertIn("candidate-run-ledger.json", smoke)
        self.assertIn("scripts.cpk_server_candidate_lifecycle declare", smoke)
        self.assertIn("scripts.cpk_server_candidate_lifecycle cleanup", smoke)
        self.assertIn("scripts.cpk_server_candidate_lifecycle success", smoke)
        self.assertIn("--ownership-ledger", smoke)
        self.assertIn("--interrupt-after", smoke)
        declaration_position = smoke.find(
            "scripts.cpk_server_candidate_lifecycle declare"
        )
        mutation_positions = tuple(
            smoke.find(token)
            for token in (
                'mkdir -p "$DIST_ROOT"',
                'cp "$CPK_CANDIDATE_ROOT/dist/control_plane_kit_core.whl"',
                'curl -fsSL "$RFC8785_WHEEL_URL"',
                "python -m scripts.cpk_server_candidate_topology",
            )
        )
        self.assertGreaterEqual(declaration_position, 0)
        self.assertTrue(all(position >= 0 for position in mutation_positions))
        if declaration_position >= 0 and all(
            position >= 0 for position in mutation_positions
        ):
            for mutation_position in mutation_positions:
                self.assertLess(declaration_position, mutation_position)
        for stale_cli_input in (
            "--foreign-canary",
            "--first-failed-stage",
            "--base-image",
        ):
            with self.subTest(stale_cli_input=stale_cli_input):
                self.assertNotIn(stale_cli_input, smoke)
        self.assertNotIn("--server-container", smoke)
        self.assertIn("timeout", smoke)
        for forbidden_cleanup in (
            'docker ps -aq --filter "label=$EVIDENCE_LABEL"',
            'docker network ls -q --filter "label=$EVIDENCE_LABEL"',
            'docker image ls -q --filter "label=$EVIDENCE_LABEL"',
            "docker system prune",
            "docker container prune",
            "docker network prune",
            "docker image prune",
        ):
            with self.subTest(forbidden_cleanup=forbidden_cleanup):
                self.assertNotIn(forbidden_cleanup, smoke)
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
        report_validation_position = smoke.find('test -s "$REPORT"')
        residue_audit_position = smoke.find("scripts/docker_residue_audit.sh")
        success_position = smoke.find(
            "scripts.cpk_server_candidate_lifecycle success"
        )
        passed_cleanup_position = smoke.find("SUPERVISOR_CLASSIFICATION=passed")
        self.assertTrue(
            all(
                position >= 0
                for position in (
                    report_validation_position,
                    residue_audit_position,
                    success_position,
                    passed_cleanup_position,
                )
            )
        )
        if all(
            position >= 0
            for position in (
                report_validation_position,
                residue_audit_position,
                success_position,
                passed_cleanup_position,
            )
        ):
            self.assertLess(report_validation_position, success_position)
            self.assertLess(residue_audit_position, success_position)
            self.assertLess(success_position, passed_cleanup_position)
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
        normalized = " ".join(
            line.strip().removesuffix("\\").strip()
            for line in test_sh.splitlines()
            if line.strip()
        )
        baseline_image = (
            'BASELINE_IMAGE="${CPK_SERVER_BASELINE_IMAGE:-'
            'localhost/control-plane-kit-servers/cpk-server:baseline}"'
        )
        candidate_image = (
            'CANDIDATE_IMAGE="${CPK_SERVER_CANDIDATE_IMAGE:-'
            'localhost/control-plane-kit-servers/cpk-server:candidate}"'
        )
        baseline_build = (
            'docker build -f products/cpk_server/Dockerfile '
            '-t "$BASELINE_IMAGE" .'
        )
        candidate_build = (
            'docker run --rm -v "$ROOT:/source:ro" -w /source '
            '-v "$CANDIDATE_STAGING_ROOT:/candidate" '
            '-v /var/run/docker.sock:/var/run/docker.sock '
            '--user "$HOST_UID:$HOST_GID" '
            '--group-add "$DOCKER_SOCKET_GID" -e HOME=/tmp '
            '"$IMAGE" python -m scripts.cpk_server_candidate_topology '
            "--package-image-only --candidate-base-image \"$BASELINE_IMAGE\" "
            "--candidate-image-tag \"$CANDIDATE_IMAGE\" "
            "--staging-root /candidate "
            "--assembly /candidate/candidate-assembly.json "
            "--inspection /candidate/candidate-inspection.json "
            "--report /candidate/candidate-topology-report.json"
        )
        candidate_smoke = (
            'CPK_SERVER_IMAGE="$CANDIDATE_IMAGE" CPK_SERVER_BUILD_IMAGE=0 '
            "sh scripts/cpk_server_image_smoke.sh"
        )

        with self.subTest(boundary="baseline-is-build-input-only"):
            self.assertEqual(test_sh.count(baseline_image), 1)
            self.assertEqual(normalized.count(baseline_build), 1)
            self.assertNotIn('CPK_SERVER_IMAGE="$BASELINE_IMAGE"', test_sh)
        with self.subTest(boundary="candidate-overlay-runner-seam"):
            self.assertEqual(test_sh.count(candidate_image), 1)
            self.assertEqual(normalized.count(candidate_build), 1)
            self.assertNotIn("scripts/cpk_server_candidate_topology_smoke.sh", test_sh)
        with self.subTest(boundary="dependency-closed-runner-python"):
            self.assertNotIn("python scripts/cpk_server_candidate_topology.py", test_sh)
            self.assertIn(
                '-v /var/run/docker.sock:/var/run/docker.sock',
                normalized,
            )
        with self.subTest(boundary="read-only-source-mount"):
            self.assertIn('-v "$ROOT:/source:ro"', normalized)
        with self.subTest(boundary="source-workdir"):
            self.assertIn('-w /source', normalized)
        with self.subTest(boundary="runner-module-invocation"):
            self.assertIn(
                '"$IMAGE" python -m scripts.cpk_server_candidate_topology',
                normalized,
            )
        with self.subTest(boundary="reject-direct-source-runner"):
            self.assertNotIn(
                "python /source/scripts/cpk_server_candidate_topology.py",
                test_sh,
            )
        with self.subTest(boundary="isolated-evidence-staging"):
            self.assertEqual(
                test_sh.count(
                    'CANDIDATE_STAGING_ROOT="$(mktemp -d '
                    "'${TMPDIR:-/tmp}/cpk-server-candidate.XXXXXX')\""
                ),
                1,
            )
            self.assertIn("--staging-root /candidate", normalized)
            self.assertIn("--assembly /candidate/candidate-assembly.json", normalized)
            self.assertIn("--inspection /candidate/candidate-inspection.json", normalized)
            self.assertEqual(
                test_sh.count(
                    'test ! -e "$CANDIDATE_STAGING_ROOT/candidate-assembly.json"'
                ),
                1,
            )
            self.assertEqual(
                test_sh.count(
                    'test ! -e "$CANDIDATE_STAGING_ROOT/candidate-inspection.json"'
                ),
                1,
            )
        with self.subTest(boundary="report-path-is-owned-staging"):
            self.assertIn(
                "--report /candidate/candidate-topology-report.json",
                normalized,
            )
        with self.subTest(boundary="report-output-collision-preflight"):
            self.assertEqual(
                test_sh.count(
                    'test ! -e "$CANDIDATE_STAGING_ROOT/'
                    'candidate-topology-report.json"'
                ),
                1,
            )
        with self.subTest(boundary="owned-docker-build-context"):
            self.assertIn('-v "$CANDIDATE_STAGING_ROOT:/candidate"', normalized)
            self.assertIn("--staging-root /candidate", normalized)
            self.assertNotIn("docker build -f acceptance/candidate_topology/Dockerfile", test_sh)
        with self.subTest(boundary="candidate-container-runs-as-host-user"):
            self.assertEqual(test_sh.count('HOST_UID="$(id -u)"'), 1)
            self.assertEqual(test_sh.count('HOST_GID="$(id -g)"'), 1)
            self.assertEqual(normalized.count('--user "$HOST_UID:$HOST_GID"'), 1)
            self.assertEqual(normalized.count('-e HOME=/tmp'), 1)
        with self.subTest(boundary="docker-socket-group-is-retained"):
            self.assertEqual(
                normalized.count(
                    "DOCKER_SOCKET_GID=\"$( docker run --rm --network none "
                    "-v /var/run/docker.sock:/var/run/docker.sock:ro "
                    "\"$IMAGE\" stat -c '%g' /var/run/docker.sock )\""
                ),
                1,
            )
            self.assertNotIn("stat -f '%g' /var/run/docker.sock", test_sh)
            self.assertEqual(
                normalized.count('--group-add "$DOCKER_SOCKET_GID"'),
                1,
            )
        with self.subTest(boundary="host-removable-candidate-staging"):
            ownership_witness = (
                'test -z "$(find "$CANDIDATE_STAGING_ROOT" '
                '! -user "$HOST_UID" -print -quit)"'
            )
            self.assertEqual(normalized.count(ownership_witness), 1)
            self.assertLess(normalized.find(candidate_build), normalized.find(ownership_witness))
            self.assertLess(
                normalized.find(ownership_witness),
                normalized.find("CANDIDATE_IMAGE_OWNED=1"),
            )
            self.assertNotIn("chmod", test_sh)
            self.assertNotIn("chown", test_sh)
        with self.subTest(boundary="owned-staging-cleanup-only"):
            self.assertEqual(
                test_sh.count('rm -rf -- "$CANDIDATE_STAGING_ROOT"'),
                1,
            )
            self.assertNotIn('rm -rf -- "$ROOT"', test_sh)
            self.assertNotIn("find \"$ROOT\" -delete", test_sh)
        with self.subTest(boundary="candidate-only-liveness"):
            self.assertEqual(normalized.count(candidate_smoke), 1)
            self.assertNotIn("CPK_SERVER_BUILD_IMAGE=1", test_sh)
        with self.subTest(boundary="candidate-before-smoke-before-residue"):
            build_position = normalized.find(candidate_build)
            smoke_position = normalized.find(candidate_smoke)
            residue_position = normalized.find("scripts/docker_residue_audit.sh")
            self.assertGreaterEqual(build_position, 0)
            self.assertGreaterEqual(smoke_position, 0)
            self.assertGreaterEqual(residue_position, 0)
            if min(build_position, smoke_position, residue_position) >= 0:
                self.assertLess(build_position, smoke_position)
                self.assertLess(smoke_position, residue_position)
        with self.subTest(boundary="package-gate-foundation"):
            self.assertIn("docker run", test_sh)
            self.assertIn("scripts/apply_coordinates.py --check", test_sh)
            self.assertIn("/test-support/package_integrity.py", test_sh)
            self.assertIn('"$POLICY_IMAGE"', test_sh)
            self.assertIn("sh -c 'cd /test-support", test_sh)
        with self.subTest(boundary="bounded-cleanup"):
            self.assertIn("trap cleanup EXIT HUP INT TERM", test_sh)
            self.assertEqual(
                test_sh.count('docker image rm "$CANDIDATE_IMAGE"'),
                1,
            )
            self.assertNotIn('docker image rm "$BASELINE_IMAGE"', test_sh)
            self.assertNotIn("docker system prune", test_sh)
            self.assertNotIn("docker volume prune", test_sh)
        with self.subTest(boundary="candidate-cleanup-requires-ownership"):
            self.assertEqual(test_sh.count("CANDIDATE_IMAGE_OWNED=0"), 1)
            self.assertEqual(test_sh.count("CANDIDATE_IMAGE_OWNED=1"), 1)
            cleanup_start = test_sh.find("cleanup() {")
            cleanup_end = test_sh.find("\n}", cleanup_start)
            cleanup_source = (
                test_sh[cleanup_start:cleanup_end]
                if min(cleanup_start, cleanup_end) >= 0
                else ""
            )
            self.assertIn(
                'if [ "$CANDIDATE_IMAGE_OWNED" = "1" ]',
                cleanup_source,
            )
            self.assertIn('docker image rm "$CANDIDATE_IMAGE"', cleanup_source)
        with self.subTest(boundary="ownership-follows-package-build"):
            build_position = normalized.find(candidate_build)
            ownership_position = normalized.find("CANDIDATE_IMAGE_OWNED=1")
            smoke_position = normalized.find(candidate_smoke)
            self.assertGreaterEqual(build_position, 0)
            self.assertGreaterEqual(ownership_position, 0)
            self.assertGreaterEqual(smoke_position, 0)
            if min(build_position, ownership_position, smoke_position) >= 0:
                self.assertLess(build_position, ownership_position)
                self.assertLess(ownership_position, smoke_position)

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
        normalized_dockerfile = dockerfile.replace("\\\n", " ")
        apt_install_runs = tuple(
            line.strip()
            for line in normalized_dockerfile.splitlines()
            if line.strip().startswith("RUN apt-get update ")
            and " apt-get install " in line
        )
        apt_install_run = apt_install_runs[0] if len(apt_install_runs) == 1 else ""
        expected_live_driver_packages = {
            "coreutils",
            "curl",
            "docker-cli",
            "git",
            "libdigest-sha-perl",
            "mawk",
        }
        apt_install_operands = (
            apt_install_run.split(" apt-get install -y --no-install-recommends ", 1)[1]
            .split(" && rm -rf /var/lib/apt/lists/*", 1)[0]
            .split()
            if " apt-get install -y --no-install-recommends " in apt_install_run
            and " && rm -rf /var/lib/apt/lists/*" in apt_install_run
            else []
        )
        for package in sorted(expected_live_driver_packages):
            with self.subTest(live_driver_package=package):
                self.assertEqual(len(apt_install_runs), 1)
                self.assertIn(
                    " apt-get install -y --no-install-recommends ",
                    apt_install_run,
                )
                self.assertEqual(
                    set(apt_install_operands),
                    expected_live_driver_packages,
                )
                self.assertIn(package, apt_install_operands)
                self.assertTrue(
                    apt_install_run.endswith(" && rm -rf /var/lib/apt/lists/*")
                )
        for executable in (
            "awk",
            "cp",
            "curl",
            "dirname",
            "docker",
            "git",
            "mkdir",
            "python",
            "pwd",
            "rm",
            "sh",
            "shasum",
            "timeout",
            "tr",
            "wc",
        ):
            with self.subTest(live_driver_executable=executable):
                self.assertIsNotNone(shutil.which(executable))

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
