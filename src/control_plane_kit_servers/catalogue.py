"""Declaration-only server product catalogue entrance.

#653 owns the full descriptor catalogue language. Until then, the catalogue is
an immutable empty assembly so package import and downstream policy can be
validated without importing product implementations.
"""

from typing import Any


def load_catalogue() -> tuple[Any, ...]:
    """Return completed server product declarations.

    The bootstrap repository intentionally has no completed products yet.
    Reserved future products are recorded in coordination metadata rather than
    returned as catalogue declarations.
    """

    return ()
