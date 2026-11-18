"""Load delivered configuration and enter the product-owned coordinator."""

import os

from control_plane_kit_server_sdk import wrapper

from . import coordinator, managed


def main() -> int:
    try:
        configuration = wrapper.load_wrapper_configuration()
        token_path = os.environ.get("TUNNEL_TOKEN_FILE")
        if type(token_path) is not str or not token_path.startswith("/") or "\x00" in token_path:
            return 1
        managed.control_configuration_artifact(configuration)
    except Exception:
        # Submitted paths, configuration and exception text are not diagnostics.
        return 1
    return coordinator.run(configuration, token_path=token_path)


if __name__ == "__main__":
    raise SystemExit(main())
