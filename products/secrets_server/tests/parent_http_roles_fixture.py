"""Real packaged provider HTTP witness; synthetic private bytes stay in memory."""
import base64
import json
from pathlib import Path
import sys

ROLES = (
    ("http-transit", "gateway.http-verification-sample-transit-signing-key", "gateway-http-verification-sample-transit"),
    ("http-workload", "workload.http-verification-sample-signing-key", "workload-http-verification-sample"),
)
WORKSPACE = "workspace-image-smoke"


class BoundedProviderClient:
    def __init__(self, client):
        self.client = client

    def post(self, path, **arguments):
        with self.client.stream("POST", path, **arguments) as response:
            raw = bytearray()
            for chunk in response.iter_bytes(chunk_size=4096):
                _require(len(raw) + len(chunk) <= 65536)
                raw.extend(chunk)
            body = json.loads(raw)
            class Result:
                status_code = response.status_code
                def json(self):
                    return body
            return Result()


def _require(condition):
    if not condition:
        raise ValueError("parent HTTP signing witness failed")


def exercise(client, private, evidence, phase):
    """Transport is real HTTP in the image lane; unit tests double transport only."""
    from source_control_fixture import read_file
    _require(phase in ("initial", "restart"))
    prior = None if phase == "initial" else json.loads(read_file(evidence / "parent-http-versions.json", 65536))
    rows = []
    for index, (role, intent, purpose) in enumerate(ROLES):
        token = read_file(private / (role + ".token"), 4096).decode("ascii")
        material = read_file(private / (role + ".key"), 4096)
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        _require(isinstance(serialization.load_pem_private_key(material, password=None), Ed25519PrivateKey))
        headers = {"Authorization":"Bearer " + token}
        path = "/v1/workspaces/" + WORKSPACE + "/secrets/" + role
        if phase == "initial":
            written = client.post(path, headers=headers, json={"value_base64":base64.b64encode(material).decode(),
                "intent":intent, "caller_subject":role, "correlation_id":role + "-write"})
            _require(written.status_code == 200)
            metadata = written.json()["metadata"]
            _require(metadata["labels"]["intent"] == intent)
            version = metadata["version_id"]
        else:
            _require(prior["schema"] == "cpk.secrets-parent-http-versions.v1")
            row = prior["roles"][index]
            _require(row["role"] == role and row["intent"] == intent)
            version = row["version_id"]
        _require(type(version) is str and 1 <= len(version) <= 256)
        request = {"intent":intent, "version_id":version, "caller_subject":role,
            "correlation_id":role + "-resolve-" + phase}
        resolved = client.post(path + "/resolve", headers=headers, json=request)
        _require(resolved.status_code == 200)
        body = resolved.json()
        _require(body["metadata"]["version_id"] == version and
            base64.b64decode(body["value_base64"], validate=True) == material)
        replay = client.post(path + "/resolve", headers=headers, json=request)
        _require(replay.status_code == 200 and replay.json() == body)
        other_role = ROLES[1-index][0]
        other_headers = {"Authorization":"Bearer " + read_file(private / (other_role + ".token"), 4096).decode("ascii")}
        for denied_path, denied_headers, correlation in (
                (path, other_headers, "wrong-role"),
                (path.replace(WORKSPACE, "foreign-workspace"), headers, "foreign-workspace")):
            denied = client.post(denied_path + "/resolve", headers=denied_headers,
                json={**request, "correlation_id":role + "-" + correlation + "-" + phase})
            _require(denied.status_code == 403 and "value_base64" not in denied.json())
            denied_write = client.post(denied_path, headers=denied_headers,
                json={"value_base64":base64.b64encode(material).decode(), "intent":intent,
                    "caller_subject":role, "correlation_id":role + "-denied-write-" + correlation + "-" + phase})
            _require(denied_write.status_code == 403 and "value_base64" not in denied_write.json())
        generation = client.post("/v1/workspaces/" + WORKSPACE + "/delegation-keys/" + role + "/generate",
            headers=headers, json={"secret_reference":"secret://control-plane-kit/" + role,
                "purpose":purpose, "issuer":"synthetic-parent", "caller_subject":role,
                "correlation_id":role + "-unsupported-generation-" + phase})
        _require(generation.status_code == 400 and generation.json()["detail"]["code"] == "invalid-delegation-key-generation"
            and "value_base64" not in generation.json())
        probe_generation = client.post("/v1/workspaces/" + WORKSPACE + "/delegation-keys/" + role + "-probe/generate",
            headers=headers, json={"secret_reference":"secret://control-plane-kit/" + role + "-probe",
                "purpose":"gateway-probe", "issuer":"synthetic-parent", "caller_subject":role,
                "correlation_id":role + "-ungranted-generation-" + phase})
        _require(probe_generation.status_code == 403 and "value_base64" not in probe_generation.json())
        rows.append({"role":role, "intent":intent, "version_id":version, "exact_version_resolved":True,
            "replay_verified":True, "wrong_role_status":403, "foreign_workspace_status":403,
            "unsupported_generation_status":400, "ungranted_generation_status":403})
    result = {"schema":"cpk.secrets-parent-http-versions.v1", "phase":phase, "roles":rows}
    if phase == "initial":
        with (evidence / "parent-http-versions.json").open("x") as stream:
            json.dump(result, stream, sort_keys=True)
    return result


if __name__ == "__main__":
    try:
        import httpx
        _require(len(sys.argv) == 2)
        with httpx.Client(base_url="http://secrets-provider:8081", timeout=5.0, trust_env=False) as client:
            result = exercise(BoundedProviderClient(client), Path("/client"), Path("/evidence"), sys.argv[1])
        print(json.dumps(result, sort_keys=True))
    except Exception:
        print("parent HTTP signing witness failed", file=sys.stderr)
        raise SystemExit(1) from None
