"""HTTP multiplexer values; process composition is loaded only when invoked."""

from .configuration import MultiplexerConfigurationError, MultiplexerSettings


def main() -> int:
    from .server import main as run
    return run()


__all__ = ["MultiplexerConfigurationError", "MultiplexerSettings", "main"]
