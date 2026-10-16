FROM python:3.12-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/cpk_server/src:/app/products/cpk_local_gateway/src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/cpk-server/control.json

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[fastapi] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/ad0582937d7e41f1e7a41295fa1de58c2ce4cba2.zip" \
    "uvicorn>=0.30" \
    "control-plane-kit-core @ https://github.com/OpenJ92/control-plane-kit/archive/87e231c661879e44816ba71ff9320c040c868d60.zip#subdirectory=control-plane-kit-core" \
    "control-plane-kit-operations @ https://github.com/OpenJ92/control-plane-kit/archive/2bd0211798c55addab1fd3135ee72371791ff566.zip#subdirectory=control-plane-kit-operations" \
    "control-plane-kit-interpreters[cloudflare,docker,gateway,public-dns] @ https://github.com/OpenJ92/control-plane-kit-interpreters/archive/0ef3c98f16382a56e4858aa822168978481b34de.zip"

COPY products/cpk_server/src ./products/cpk_server/src
COPY products/cpk_local_gateway/src ./products/cpk_local_gateway/src

RUN adduser --disabled-password --gecos "" --uid 10001 cpk \
    && chown -R cpk:cpk /app

USER 10001
EXPOSE 8080

CMD ["python", "-m", "control_plane_kit_servers_cpk_server.server"]
