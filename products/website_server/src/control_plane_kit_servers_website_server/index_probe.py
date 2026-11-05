"""Build-owned expected index and one fixed, bounded local HTTP comparison."""
from dataclasses import dataclass
from hashlib import sha256
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
from threading import Event, Timer
import time

from control_plane_kit_core import NodeHealthReadOutcome as Outcome

EXPECTATION_PATH = "/app/website-index.json"
MAX_INDEX_BYTES = 5 * 1048576
PROBE_SECONDS = 1.0
MIME = "text/html; charset=utf-8"


@dataclass(frozen=True)
class IndexExpectation:
    length: int
    digest: str

    def __post_init__(self):
        if type(self.length) is not int or not 1 <= self.length <= MAX_INDEX_BYTES:
            raise ValueError("Website index expectation is invalid")
        if type(self.digest) is not str or re.fullmatch("[0-9a-f]{64}", self.digest) is None:
            raise ValueError("Website index expectation is invalid")


def load_expectation():
    try:
        descriptor = os.open(EXPECTATION_PATH, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_mode & 0o222:
                return None
            encoded = stream.read(513)
        if len(encoded) > 512:
            return None
        value = json.loads(encoded)
        if set(value) != {"schema", "length", "sha256"} or value["schema"] != "cpk.website-index.v1":
            return None
        return IndexExpectation(value["length"],value["sha256"])
    except (OSError, ValueError, TypeError):
        return None


def read_index(expected):
    connection = http.client.HTTPConnection("127.0.0.1", 8080, timeout=PROBE_SECONDS)
    expired = Event()
    deadline = time.monotonic() + PROBE_SECONDS

    def expire():
        expired.set()
        current = connection.sock
        if current is not None:
            try:
                current.shutdown(socket.SHUT_RDWR)
            except OSError:
                return

    timer = Timer(PROBE_SECONDS, expire)
    timer.daemon = True
    timer.start()
    try:
        connection.request("GET", "/index.html", headers={"Accept":"text/html", "Connection":"keep-alive"})
        # Keep a direct socket reference: HTTPConnection may detach it on a
        # Connection: close reply while its response file still reads the body.
        current = connection.sock
        response = connection.getresponse()
        if (response.status != 200 or response.getheader("Content-Type") != MIME
                or response.getheader("Content-Length") != str(expected.length)
                or response.getheader("Content-Encoding") not in (None,"identity")):
            return Outcome.UNKNOWN if expired.is_set() else Outcome.UNHEALTHY
        digest = sha256()
        size = 0
        while size <= expected.length:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return Outcome.UNKNOWN
            if current is not None and current.fileno() >= 0:
                current.settimeout(remaining)
            chunk = response.read1(min(65536,expected.length + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
        if expired.is_set():
            return Outcome.UNKNOWN
        return Outcome.HEALTHY if size == expected.length and digest.hexdigest() == expected.digest else Outcome.UNHEALTHY
    except (OSError, http.client.HTTPException, ValueError):
        return Outcome.UNKNOWN
    finally:
        timer.cancel()
        connection.close()


def build_expectation():
    content = Path("/app/dist/index.html").read_bytes()
    expected = IndexExpectation(len(content),sha256(content).hexdigest())
    target = Path(EXPECTATION_PATH)
    target.write_text(json.dumps({"schema":"cpk.website-index.v1","length":expected.length,
                                  "sha256":expected.digest},sort_keys=True))
    target.chmod(0o444)


if __name__ == "__main__":
    build_expectation()
