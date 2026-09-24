FROM cloudflare/cloudflared:2026.6.1@sha256:6d91c121b803126f7a5344005d17a9324788fc09d305b6e2560ec6040a7ae283 AS native

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/products/cloudflared_connector/src
COPY --from=native /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY products/cloudflared_connector/src /app/products/cloudflared_connector/src
USER 65532:65532
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=5s --timeout=3s --retries=1 \
    CMD ["python", "-m", "control_plane_kit_servers_cloudflared_connector.readiness"]
ENTRYPOINT ["cloudflared", "--no-autoupdate", "--metrics", "127.0.0.1:20241"]
CMD ["tunnel", "run"]
