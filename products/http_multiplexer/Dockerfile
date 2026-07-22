FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/products/http_multiplexer/src
ENV PORT=8000

WORKDIR /app

RUN useradd --create-home --uid 10004 multiplexer

COPY products/http_multiplexer/src /app/products/http_multiplexer/src

USER multiplexer
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_http_multiplexer.server"]
