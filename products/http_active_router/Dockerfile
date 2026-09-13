FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/products/http_active_router/src
ENV PORT=8000

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/2b10d5a354ba4da9407d336703aacb96910100d4.zip"

RUN useradd --create-home --uid 10003 router

COPY products/http_active_router/src /app/products/http_active_router/src

USER router
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_http_active_router.server"]
