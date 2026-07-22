"""Declaration-only server product catalogue and publication helpers.

The catalogue is publication metadata for completed server products. It is not a
second product descriptor language and it never imports product application code.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


SCHEMA = "cpk-servers.descriptor-catalogue"
DEFAULT_CATALOGUE_PATH = Path(__file__).with_name("catalogue.json")
PRODUCT_KEYS = frozenset(
    {
        "product_id",
        "owner_directory",
        "descriptor_path",
        "descriptor_sha256",
        "source_commit",
        "image_ref",
        "image_digest",
        "status",
    }
)


class CatalogueError(ValueError):
    """Raised when publication catalogue data is invalid."""


@dataclass(frozen=True, slots=True)
class PublishedProductDescriptor:
    """Immutable publication record for one completed server product."""

    product_id: str
    owner_directory: str
    descriptor_path: str
    descriptor_sha256: str
    source_commit: str
    image_ref: str
    image_digest: str
    status: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PublishedProductDescriptor":
        if not isinstance(value, Mapping):
            raise CatalogueError("catalogue product must be an object")
        keys = frozenset(value)
        unknown = keys - PRODUCT_KEYS
        missing = PRODUCT_KEYS - keys
        if unknown:
            raise CatalogueError(f"unknown product keys: {sorted(unknown)}")
        if missing:
            raise CatalogueError(f"missing product keys: {sorted(missing)}")

        descriptor = cls(
            product_id=_required_string(value, "product_id"),
            owner_directory=_required_string(value, "owner_directory"),
            descriptor_path=_required_string(value, "descriptor_path"),
            descriptor_sha256=_required_string(value, "descriptor_sha256"),
            source_commit=_required_string(value, "source_commit"),
            image_ref=_required_string(value, "image_ref"),
            image_digest=_required_string(value, "image_digest"),
            status=_required_string(value, "status"),
        )
        descriptor._validate()
        return descriptor

    def descriptor(self) -> dict[str, str]:
        return {
            "product_id": self.product_id,
            "owner_directory": self.owner_directory,
            "descriptor_path": self.descriptor_path,
            "descriptor_sha256": self.descriptor_sha256,
            "source_commit": self.source_commit,
            "image_ref": self.image_ref,
            "image_digest": self.image_digest,
            "status": self.status,
        }

    def _validate(self) -> None:
        if self.status != "completed":
            raise CatalogueError("catalogue contains only completed declarations")
        _validate_relative_path("owner_directory", self.owner_directory)
        _validate_relative_path("descriptor_path", self.descriptor_path)
        if not _is_lower_hex(self.descriptor_sha256, 64):
            raise CatalogueError("descriptor_sha256 must be 64 lowercase hex characters")
        if not _is_lower_hex(self.source_commit, 40):
            raise CatalogueError("source_commit must be 40 lowercase hex characters")
        if not self.image_ref:
            raise CatalogueError("image_ref is required")
        if not self.image_digest.startswith("sha256:") or not _is_lower_hex(
            self.image_digest.removeprefix("sha256:"), 64
        ):
            raise CatalogueError("image_digest must be a sha256 digest")


def load_catalogue(
    path: str | Path | None = None,
) -> tuple[PublishedProductDescriptor, ...]:
    """Load completed server product publication records."""

    catalogue_path = Path(path) if path is not None else DEFAULT_CATALOGUE_PATH
    raw = _read_catalogue(catalogue_path)
    products = raw.get("products")
    if not isinstance(products, list):
        raise CatalogueError("catalogue products must be a list")

    declarations = tuple(PublishedProductDescriptor.from_mapping(item) for item in products)
    seen: set[str] = set()
    for declaration in declarations:
        if declaration.product_id in seen:
            raise CatalogueError(f"duplicate product_id: {declaration.product_id}")
        seen.add(declaration.product_id)
    return tuple(sorted(declarations, key=lambda item: item.product_id))



def load_product_catalog(
    path: str | Path,
    *,
    root: str | Path,
):
    """Load completed publication records as a core ProductCatalog.

    This is the explicit descriptor admission boundary. It validates publication
    metadata against descriptor bytes without importing product process code.
    """

    from control_plane_kit_core.products import ProductCatalog, ProductDescriptorCodec

    catalogue_path = Path(path)
    root_path = Path(root)
    codec = ProductDescriptorCodec()
    documents = []
    for declaration in load_catalogue(catalogue_path):
        descriptor_path = root_path / declaration.descriptor_path
        content = descriptor_path.read_bytes()
        descriptor_digest = hashlib.sha256(content).hexdigest()
        if descriptor_digest != declaration.descriptor_sha256:
            raise CatalogueError(
                f"descriptor digest mismatch for {declaration.product_id}"
            )
        document = codec.decode_document(content)
        if document.product.image.digest != declaration.image_digest:
            raise CatalogueError(f"image digest mismatch for {declaration.product_id}")
        documents.append(document)
    return ProductCatalog.from_documents(documents)

def publish_catalogue(source: str | Path, output: str | Path) -> dict[str, Any]:
    """Write deterministic publication JSON and a sha256 sidecar."""

    declarations = load_catalogue(source)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": SCHEMA,
        "products": [item.descriptor() for item in declarations],
    }
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    output_path.write_bytes(encoded)
    checksum = hashlib.sha256(encoded).hexdigest()
    output_path.with_suffix(output_path.suffix + ".sha256").write_text(
        f"{checksum}  {output_path.name}\n",
        encoding="utf-8",
    )
    return {
        "schema": "cpk-servers.descriptor-catalogue-publication-report",
        "output": str(output_path),
        "checksum": checksum,
        "product_ids": [item.product_id for item in declarations],
    }


def _read_catalogue(path: Path) -> Mapping[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise CatalogueError(f"catalogue file does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise CatalogueError(f"catalogue JSON is invalid: {path}") from error
    if not isinstance(raw, dict):
        raise CatalogueError("catalogue root must be an object")
    keys = frozenset(raw)
    unknown = keys - {"schema", "products"}
    if unknown:
        raise CatalogueError(f"unknown catalogue keys: {sorted(unknown)}")
    if raw.get("schema") != SCHEMA:
        raise CatalogueError(f"catalogue schema must be {SCHEMA}")
    return raw


def _required_string(value: Mapping[str, Any], key: str) -> str:
    candidate = value[key]
    if not isinstance(candidate, str) or candidate == "":
        raise CatalogueError(f"{key} must be a nonempty string")
    return candidate


def _validate_relative_path(name: str, value: str) -> None:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise CatalogueError(f"{name} must be a safe relative path")


def _is_lower_hex(value: str, length: int) -> bool:
    return len(value) == length and all(char in "0123456789abcdef" for char in value)
