FROM postgres@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/postgres_server/src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/postgres/control.json \
    POSTGRES_DB=cpk \
    POSTGRES_USER=cpk \
    POSTGRES_PASSWORD_FILE=/run/secrets/postgres/password \
    PGDATA=/var/lib/postgresql/data

WORKDIR /app

RUN apk add --no-cache python3 py3-pip \
    && python3 -m pip install --break-system-packages --no-cache-dir \
      "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/cad5cc3dacbff1da79e6cc8b4c0c88526363e033.zip"

COPY products/postgres_server/src ./products/postgres_server/src

USER 70:70
EXPOSE 5432 8000
STOPSIGNAL SIGTERM
ENTRYPOINT []
CMD ["python3", "-m", "control_plane_kit_servers_postgres_server.process"]
