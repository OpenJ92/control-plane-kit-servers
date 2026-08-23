ARG CPK_SERVER_BASE_IMAGE
FROM ${CPK_SERVER_BASE_IMAGE}
USER root

COPY dist/control_plane_kit_core.whl /tmp/control_plane_kit_core-0.1.0-py3-none-any.whl
COPY dist/control_plane_kit_operations.whl /tmp/control_plane_kit_operations-0.1.0-py3-none-any.whl
COPY dist/rfc8785-0.1.4-py3-none-any.whl /tmp/rfc8785-0.1.4-py3-none-any.whl
RUN python -m pip install --force-reinstall --no-deps --no-index \
    /tmp/control_plane_kit_core-0.1.0-py3-none-any.whl \
    /tmp/control_plane_kit_operations-0.1.0-py3-none-any.whl \
    /tmp/rfc8785-0.1.4-py3-none-any.whl \
    && rm -f \
        /tmp/control_plane_kit_core-0.1.0-py3-none-any.whl \
        /tmp/control_plane_kit_operations-0.1.0-py3-none-any.whl \
        /tmp/rfc8785-0.1.4-py3-none-any.whl
USER cpk
