from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from control_plane_kit_servers.catalogue import publish_catalogue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Publish server product catalogue")
    parser.add_argument("--catalogue", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    report = publish_catalogue(args.catalogue, args.out)
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
