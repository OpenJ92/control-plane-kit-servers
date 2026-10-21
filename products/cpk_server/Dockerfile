FROM python:3.12-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/cpk_server/src:/app/products/cpk_local_gateway/src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/cpk-server/control.json

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[fastapi] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/cad5cc3dacbff1da79e6cc8b4c0c88526363e033.zip" \
    "uvicorn>=0.30" \
    "control-plane-kit-core @ https://github.com/OpenJ92/control-plane-kit/archive/955666898218e4f2956b6e9fcd33bdba97ffdb06.zip#subdirectory=control-plane-kit-core" \
    "control-plane-kit-operations @ https://github.com/OpenJ92/control-plane-kit/archive/955666898218e4f2956b6e9fcd33bdba97ffdb06.zip#subdirectory=control-plane-kit-operations" \
    "control-plane-kit-interpreters[cloudflare,docker,gateway,public-dns] @ https://github.com/OpenJ92/control-plane-kit-interpreters/archive/528fb20692400c01e107f86b3952a52a70883652.zip"

COPY products/cpk_server/src ./products/cpk_server/src
COPY products/cpk_local_gateway/src ./products/cpk_local_gateway/src

RUN adduser --disabled-password --gecos "" --uid 10001 cpk \
    && chown -R cpk:cpk /app

USER 10001
EXPOSE 8080

CMD ["python", "-m", "control_plane_kit_servers_cpk_server.server"]
