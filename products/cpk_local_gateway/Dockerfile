FROM python:3.12-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/cpk_local_gateway/src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/gateway/control.json \
    CPK_GATEWAY_TARGETS_JSON="{}"

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-core @ https://github.com/OpenJ92/control-plane-kit/archive/ec61e2b17c3a3f1bdea1dd6bc8fc64ac1b9528b0.zip#subdirectory=control-plane-kit-core" \
    "control-plane-kit-server-sdk[fastapi] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/eff09090755eb21028695f0224eec7b81f2db535.zip" \
    "fastapi>=0.115" \
    "PyJWT[crypto]>=2.10" \
    "uvicorn>=0.30" \
    "httpx>=0.27,<1" \
    "psycopg[binary]>=3.2"

COPY products/cpk_local_gateway/src ./products/cpk_local_gateway/src

RUN adduser --disabled-password --gecos "" --uid 10005 gateway \
    && chown -R gateway:gateway /app

USER gateway
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_cpk_local_gateway.server"]
