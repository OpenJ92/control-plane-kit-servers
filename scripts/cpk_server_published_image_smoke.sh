#!/bin/sh
set -eu

default_image() {
  python3 - <<'PY'
import json
from pathlib import Path

image = json.loads(Path("products/cpk_server/product.cpk.json").read_text())["product"]["image"]
print(f"{image['registry']}/{image['repository']}@{image['digest']}")
PY
}

CPK_SERVER_IMAGE="${CPK_SERVER_IMAGE:-$(default_image)}"
export CPK_SERVER_IMAGE
export CPK_SERVER_BUILD_IMAGE=0

docker pull "$CPK_SERVER_IMAGE" >/dev/null
sh scripts/cpk_server_image_smoke.sh

echo "cpk-server published image smoke passed"
