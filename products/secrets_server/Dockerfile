FROM python:3.12-slim

ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PYTHONDONTWRITEBYTECODE=1 \
    CPK_SECRETS_DATABASE_PATH=/var/lib/cpk-secrets/secrets.sqlite3 \
    CPK_SECRETS_PROVIDER_ID=control-plane-kit \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/secrets-server/control.json \
    PYTHONPATH=/opt/cpk-secrets-product

COPY products/secrets_server/entrypoint.sh /usr/local/bin/cpk-secrets-entrypoint
COPY products/secrets_server/src/control_plane_kit_servers_secrets_server /opt/cpk-secrets-product/control_plane_kit_servers_secrets_server

RUN python -m pip install --no-cache-dir \
    "control-plane-kit-secrets @ https://github.com/OpenJ92/control-plane-kit-secrets/archive/158b17ed10689360c4e1529a395b3ee2b47aecbc.zip" \
    "uvicorn>=0.35" \
    && adduser --disabled-password --gecos "" --uid 10006 secrets \
    && chmod 0555 /usr/local/bin/cpk-secrets-entrypoint \
    && install -d -o secrets -g secrets -m 0700 \
        /run/secrets/cpk-secrets \
        /var/lib/cpk-secrets \
    && install -d -m 0755 /etc/cpk/secrets-server

USER 10006
EXPOSE 8081

ENTRYPOINT ["cpk-secrets-entrypoint"]
CMD ["uvicorn", "control_plane_kit_servers_secrets_server.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8081"]
