"""Target interface for Servers #228, not an implemented observation.

This scaffold makes the target-red checkpoint fail on missing behavior rather
than package collection/import setup. It must not be merged or published.
"""


def classify_response(status: int, body: bytes):
    raise NotImplementedError("bounded native response classification is missing")


def read_connection():
    raise NotImplementedError("fixed loopback connection observation is missing")


def main() -> int:
    raise NotImplementedError("bounded connection output is missing")
