from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_report(inventory_path: Path) -> dict[str, Any]:
    root = inventory_path.resolve().parents[1]
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
        image_source = product.get("image_source", "local-dockerfile")
        if image_source == "local-dockerfile":
            dockerfile = product.get("dockerfile")
            if not isinstance(dockerfile, str) or not dockerfile:
                raise ValueError("local image products require dockerfile")
            dockerfile_path = root / dockerfile
            status = (
                "image-definition-present"
                if dockerfile_path.exists()
                else "requires-product-local-image-definition"
            )
            image_builds.append(
                {
                    "product_id": product_id,
                    "image_source": image_source,
                    "dockerfile": dockerfile,
                    "status": status,
                }
            )
        elif image_source == "external-oci":
            image_ref = product.get("external_image")
            if not isinstance(image_ref, str) or "@sha256:" not in image_ref:
                raise ValueError("external OCI products require digest-pinned external_image")
            image_builds.append(
                {
                    "product_id": product_id,
                    "image_source": image_source,
                    "external_image": image_ref,
                    "status": "external-oci-pinned",
                }
            )
        else:
            raise ValueError(f"unknown product image_source: {image_source}")

    return {
        "schema": "cpk-servers.product-image-lane-report",
        "products": products,
        "image_builds": image_builds,
        "status": (
            "no-products"
            if not products
            else (
                "product-image-definitions-present"
                if all(
                    item["status"]
                    in {"image-definition-present", "external-oci-pinned"}
                    for item in image_builds
                )
                else "product-image-definitions-required"
            )
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    args = parser.parse_args()

    print(json.dumps(build_report(args.inventory), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
