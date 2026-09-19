"""HTTP active-router values; process composition is loaded only when invoked."""

from .configuration import RouterConfigurationError, RouterSettings


def main() -> int:
    from .server import main as run
    return run()


__all__ = ["RouterConfigurationError", "RouterSettings", "main"]
