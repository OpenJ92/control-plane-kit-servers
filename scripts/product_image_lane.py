from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_report(inventory_path: Path) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    products = inventory.get("products")
    if not isinstance(products, list):
        raise ValueError("product inventory must contain a products list")

    image_builds = []
    for product in products:
        if not isinstance(product, dict):
            raise ValueError("product entries must be objects")
        product_id = product.get("product_id")
        if not isinstance(product_id, str) or not product_id:
            raise ValueError("product entries require product_id")
        image_builds.append(
            {
                "product_id": product_id,
                "status": "requires-product-local-image-definition",
            }
        )

    return {
        "schema": "cpk-servers.product-image-lane-report",
        "products": products,
        "image_builds": image_builds,
        "status": "no-products" if not products else "product-image-definitions-required",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    args = parser.parse_args()

    print(json.dumps(build_report(args.inventory), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
