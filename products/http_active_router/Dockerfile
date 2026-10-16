FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/products/http_active_router/src
ENV PORT=8000
ENV CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/router/control.json

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/ad0582937d7e41f1e7a41295fa1de58c2ce4cba2.zip"

RUN useradd --create-home --uid 10003 router

COPY products/http_active_router/src /app/products/http_active_router/src

USER router
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_http_active_router.server"]
