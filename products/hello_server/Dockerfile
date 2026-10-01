FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/hello_server/src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/hello/control.json \
    HELLO_MESSAGE="Hello, world!" \
    HELLO_COLOR="blue" \
    HELLO_DEPENDENCIES_JSON="[]"

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/5dc93b92c27bb9bbe2af027f945a347e5e4131bc.zip"

COPY products/hello_server/src ./products/hello_server/src

RUN adduser --disabled-password --gecos "" --uid 10002 hello \
    && chown -R hello:hello /app

USER hello
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_hello_server.server"]
