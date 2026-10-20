"""Explicit product-owned native connection composition."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True, repr=False)
class DockerManagedNativeConnection:
    endpoints: object
    product_document: object
    clock: object

    def select(self, *, plan, current, desired, registered_products, runtime_authorities):
        raise NotImplementedError("managed native composition is not implemented")

    async def observe_connection(self, realization, request, authority):
        raise NotImplementedError("managed native composition is not implemented")
