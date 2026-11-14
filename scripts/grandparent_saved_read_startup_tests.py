"""Offline physical-mount startup probe; synthetic inputs and intercepted wire."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
from unittest.mock import patch


def make_fixture(directory):
    sys.path.insert(0, "/source/scripts")
    import grandparent_cpk_cutover as action
    import grandparent_saved_read as verification
    from grandparent_cutover_installer_tests import HUMAN, SYNTHETIC_GRAPH
    baseline = action.canonical(SYNTHETIC_GRAPH)
    plan = dict(schema="cpk399.read-only-approval.v1", run=verification.RUN, read_once_approved=True,
        reader_sha256=hashlib.sha256(Path(verification.__file__).read_bytes()).hexdigest(),
        shared_reader_sha256=hashlib.sha256(Path(action.__file__).read_bytes()).hexdigest(),
        endpoint="http://127.0.0.1:18163", routes=list(action.READ_ROUTES.values()))
    raw_plan = action.canonical(plan)
    for name, raw, mode in (("action.json", raw_plan, 0o600), ("desired.json", baseline, 0o644),
                           ("human.bearer", HUMAN.encode(), 0o400)):
        target = directory / name
        with target.open("xb") as stream:
            stream.write(raw)
        target.chmod(mode)
    (directory / "expected.json").write_text(json.dumps(dict(
        plan_sha256=hashlib.sha256(raw_plan).hexdigest(), baseline_sha256=hashlib.sha256(baseline).hexdigest())))


def probe():
    # Root-file module paths match the live launch. Test support is added only
    # after loading them; installed product modules are never source-overlaid.
    sys.path.insert(0, "/")
    import grandparent_cpk_cutover as action
    import grandparent_saved_read as verification
    sys.path.insert(1, "/source/scripts")
    from grandparent_cutover_installer_tests import Wire
    from control_plane_kit_servers_cpk_server.client import transport
    expected = json.loads(Path("/fixture/expected.json").read_text())
    paths = {"proposal": "/proposal/verification.json", "reader-source": "/grandparent_saved_read.py",
             "shared-source": "/grandparent_cpk_cutover.py", "baseline": "/public/desired.json",
             "credential": "/credentials/human.bearer", "proposal-parent": "/proposal",
             "baseline-parent": "/public", "credential-parent": "/credentials"}
    metadata = {}
    for role, name in paths.items():
        try:
            value = Path(name).stat()
            metadata[role] = dict(uid=value.st_uid, gid=value.st_gid, mode=stat.S_IMODE(value.st_mode),
                                  readable=os.access(name, os.R_OK), searchable=os.access(name, os.X_OK))
        except OSError:
            metadata[role] = dict(metadata_unavailable=True)
    observed = dict(last_stage="entry", first_failure=None)
    def failure(stage, error):
        if observed["first_failure"] is None:
            name = type(error).__name__
            observed["first_failure"] = dict(stage=stage, category=name if name in {
                "PermissionError", "FileNotFoundError", "Hold", "ReadFailure", "ClientConfigurationError"} else "other",
                errno=error.errno if isinstance(error, OSError) and error.errno in {1, 2, 13, 30} else None)
    original_read, original_require = Path.read_bytes, verification.require
    def actual_read(target):
        stage = next((role + "-read" for role, name in paths.items() if str(target) == name), "other-public-read")
        observed["last_stage"] = stage
        try:
            return original_read(target)
        except BaseException as error:
            failure(stage, error)
            raise
    def checked(value, code):
        observed["last_stage"] = code if code in {"invocation", "reader-owner", "plan-digest", "authority",
            "proxy-environment", "baseline-digest", "baseline-shape"} else "other-guard"
        try:
            return original_require(value, code)
        except BaseException as error:
            failure(observed["last_stage"], error)
            raise
    def observe_call(original, stage):
        def call(reader, *args, **kwargs):
            observed["last_stage"] = stage
            try:
                return original(reader, *args, **kwargs)
            except BaseException as error:
                failure(stage, error)
                raise
        return call
    wire_root = Path("/tmp/startup-wire")
    wire_root.mkdir()
    with patch.object(Path, "read_bytes", actual_read), patch.object(verification, "require", checked), \
            patch.object(verification, "BASELINE_SHA", expected["baseline_sha256"]), \
            patch.object(action.SavedReads, "__init__", observe_call(action.SavedReads.__init__, "credential-metadata")), \
            patch.object(action.SavedReads, "owner_credential", observe_call(action.SavedReads.owner_credential, "credential-loader")), \
            patch.object(action.SavedReads, "saved", observe_call(action.SavedReads.saved, "saved-reads")), \
            patch.object(transport, "build_opener", return_value=Wire(wire_root / "human.bearer", diagnosis="verification")), \
            patch.object(sys, "argv", ["/grandparent_saved_read.py", "--verify-saved-read-only", expected["plan_sha256"]]), \
            redirect_stdout(io.StringIO()) as output:
        status = verification.main()
    result = json.loads(output.getvalue())
    assert status in {0, 1} and result["status"] in {"verified", "HOLD"}
    print("physical-startup-diagnostic " + json.dumps(dict(schema="cpk399.offline-startup.v1",
        uid=os.getuid(), gid=os.getgid(), main_exit=status, program_status=result["status"],
        completed_reads=result["completed_reads"], observation=observed,
        program_stage=result.get("stage"), program_failure_category=result.get("failure_category"),
        untraced_failure=status != 0 and observed["first_failure"] is None, input_metadata=metadata,
        environment=dict(proxy_nonempty=any(v for k, v in os.environ.items() if k.lower() in {
            "http_proxy", "https_proxy", "all_proxy"}), pythonpath_present=bool(os.environ.get("PYTHONPATH")),
            home_present=bool(os.environ.get("HOME")), cwd_is_image_default=os.getcwd() == "/app"),
        synthetic_baseline_pin=True, real_file_reads=True, network="none", wire_intercepted=True,
        production_source_changed=False, live_acceptance=False), sort_keys=True))


if __name__ == "__main__":
    assert (os.getuid(), os.getgid()) == (501, 20)
    if sys.argv[1:] == ["--make-fixture", "/fixture"]:
        make_fixture(Path("/fixture"))
    elif sys.argv[1:] == ["--probe"]:
        probe()
    else:
        raise SystemExit(2)
