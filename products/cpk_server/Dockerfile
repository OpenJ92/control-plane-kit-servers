FROM python:3.12-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/cpk_server/src:/app/products/cpk_local_gateway/src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/cpk-server/control.json

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[fastapi] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/43838fd0f4391428cfffa87f8c4dbd5cc6d5eab1.zip" \
    "uvicorn>=0.30" \
    "control-plane-kit-core @ https://github.com/OpenJ92/control-plane-kit/archive/4cc1716bef4d7548ddb4cd343e53fa06bb447104.zip#subdirectory=control-plane-kit-core" \
    "control-plane-kit-operations @ https://github.com/OpenJ92/control-plane-kit/archive/4cc1716bef4d7548ddb4cd343e53fa06bb447104.zip#subdirectory=control-plane-kit-operations" \
    "control-plane-kit-interpreters[cloudflare,docker,gateway,public-dns] @ https://github.com/OpenJ92/control-plane-kit-interpreters/archive/c8ec929efe648408d247ac5462a1f4be96fb8c11.zip"

COPY products/cpk_server/src ./products/cpk_server/src
COPY products/cpk_local_gateway/src ./products/cpk_local_gateway/src

RUN adduser --disabled-password --gecos "" --uid 10001 cpk \
    && chown -R cpk:cpk /app

USER 10001
EXPOSE 8080

CMD ["python", "-m", "control_plane_kit_servers_cpk_server.server"]
