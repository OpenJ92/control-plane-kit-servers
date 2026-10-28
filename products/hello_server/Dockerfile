FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/hello_server/src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/hello/control.json \
    HELLO_MESSAGE="Hello, world!" \
    HELLO_COLOR="blue" \
    HELLO_DEPENDENCIES_JSON="[]"

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/cd4722fbfb942e7c2467a39b3cd0e32ded4a90ac.zip"

COPY products/hello_server/src ./products/hello_server/src

RUN adduser --disabled-password --gecos "" --uid 10002 hello \
    && chown -R hello:hello /app

USER hello
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_hello_server.server"]
