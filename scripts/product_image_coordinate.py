from __future__ import annotations

import json
from pathlib import Path
import re
import sys
from typing import Mapping


ROOT = Path(__file__).resolve().parents[1]
COORDINATES = ROOT / "coordinates" / "server-products.json"


class ProductCoordinateError(ValueError):
    """Raised when an immutable product image coordinate cannot be selected."""


def image_execution_reference(path: Path, product_id: str) -> str:
    product = _product_coordinate(path, product_id)
    image = product.get("image")
    if not isinstance(image, Mapping):
        raise ProductCoordinateError("product image coordinate must be an object")
    registry = _text(image, "registry")
    repository = _text(image, "repository")
    digest = _text(image, "digest")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise ProductCoordinateError("product image digest must be canonical SHA-256")
    return f"{registry}/{repository}@{digest}"


def product_source_commit(path: Path, product_id: str) -> str:
    product = _product_coordinate(path, product_id)
    source_commit = _text(product, "source_commit")
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None:
        raise ProductCoordinateError("product source commit must be canonical")
    return source_commit


def _product_coordinate(path: Path, product_id: str) -> Mapping[str, object]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping) or document.get("schema") != "cpk-servers.coordinates":
        raise ProductCoordinateError("coordinate document has an unsupported schema")
    products = document.get("products")
    if not isinstance(products, list):
        raise ProductCoordinateError("coordinate products must be a list")
    matches = [
        value
        for value in products
        if isinstance(value, Mapping) and value.get("product_id") == product_id
    ]
    if len(matches) != 1:
        raise ProductCoordinateError("product coordinate must exist exactly once")
    return matches[0]


def _text(value: Mapping[str, object], key: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate:
        raise ProductCoordinateError(f"product image {key} must be non-empty text")
    return candidate


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) == 1:
        value = image_execution_reference(COORDINATES, arguments[0])
    elif len(arguments) == 2 and arguments[0] == "--source-commit":
        value = product_source_commit(COORDINATES, arguments[1])
    else:
        raise ProductCoordinateError(
            "provide one product id or --source-commit plus one product id"
        )
    print(value)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProductCoordinateError as error:
        print(f"coordinate error: {error}", file=sys.stderr)
        raise SystemExit(1) from error
