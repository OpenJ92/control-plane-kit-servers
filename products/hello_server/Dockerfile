FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/hello_server/src \
    HELLO_MESSAGE="Hello, world!" \
    HELLO_DEPENDENCIES_JSON="[]"

WORKDIR /app

COPY products/hello_server/src ./products/hello_server/src

RUN adduser --disabled-password --gecos "" --uid 10002 hello \
    && chown -R hello:hello /app

USER hello
EXPOSE 8000

CMD ["python", "-m", "control_plane_kit_servers_hello_server.server"]
