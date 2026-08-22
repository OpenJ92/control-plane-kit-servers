ARG CPK_SERVER_BASE_IMAGE
FROM ${CPK_SERVER_BASE_IMAGE}

COPY dist/control_plane_kit_core.whl /tmp/control_plane_kit_core.whl
COPY dist/control_plane_kit_operations.whl /tmp/control_plane_kit_operations.whl
RUN python -m pip install --force-reinstall --no-deps --no-index \
    /tmp/control_plane_kit_core.whl \
    /tmp/control_plane_kit_operations.whl \
    && rm -f /tmp/control_plane_kit_core.whl /tmp/control_plane_kit_operations.whl
