"""Public import surface for control-plane-kit server products."""

from .catalogue import load_catalogue

__version__ = "0.1.0"

__all__ = (
    "__version__",
    "load_catalogue",
)
