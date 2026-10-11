FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/products/http_multiplexer/src
ENV PORT=8000
ENV CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/multiplexer/control.json

WORKDIR /app

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/23500b1445dc6a748bd92a441e781d7f9ed90299.zip"

RUN useradd --create-home --uid 10004 multiplexer

COPY products/http_multiplexer/src /app/products/http_multiplexer/src

USER multiplexer
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_http_multiplexer.server"]
