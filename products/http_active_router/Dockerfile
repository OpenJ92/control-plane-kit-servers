FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/products/http_active_router/src
ENV PORT=8000

WORKDIR /app

RUN useradd --create-home --uid 10003 router

COPY products/http_active_router/src /app/products/http_active_router/src

USER router
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_http_active_router.server"]
