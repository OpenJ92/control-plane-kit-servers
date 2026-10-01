FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/products/http_multiplexer/src
ENV PORT=8000
ENV CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/multiplexer/control.json

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/5dc93b92c27bb9bbe2af027f945a347e5e4131bc.zip"

RUN useradd --create-home --uid 10004 multiplexer

COPY products/http_multiplexer/src /app/products/http_multiplexer/src

USER multiplexer
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_http_multiplexer.server"]
