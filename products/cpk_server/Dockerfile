FROM python:3.12-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/cpk_server/src

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "fastapi>=0.115" \
    "uvicorn>=0.30" \
    "control-plane-kit-core @ https://github.com/OpenJ92/control-plane-kit/archive/087a89253b14b3bb438af9042ea779976886a79e.zip#subdirectory=control-plane-kit-core" \
    "control-plane-kit-operations @ https://github.com/OpenJ92/control-plane-kit/archive/087a89253b14b3bb438af9042ea779976886a79e.zip#subdirectory=control-plane-kit-operations" \
    "control-plane-kit-interpreters[cloudflare,docker,gateway,public-dns] @ https://github.com/OpenJ92/control-plane-kit-interpreters/archive/107f55e29e193d89e829bc350a039fc41b1adf81.zip"

COPY products/cpk_server/src ./products/cpk_server/src

RUN adduser --disabled-password --gecos "" --uid 10001 cpk \
    && chown -R cpk:cpk /app

USER 10001
EXPOSE 8080

CMD ["python", "-m", "control_plane_kit_servers_cpk_server.server"]
