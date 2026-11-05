# The caller selects and qualifies the ordinary Web image by immutable digest.
ARG WEBSITE_IMAGE
FROM ${WEBSITE_IMAGE}
ARG VCS_REF
LABEL org.opencontainers.image.source="https://github.com/OpenJ92/control-plane-kit-servers" \
      org.opencontainers.image.revision=$VCS_REF
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/cpk-website
RUN /opt/cpk-website/bin/pip install --no-cache-dir \
    "control-plane-kit-server-sdk[verification] @ https://github.com/OpenJ92/control-plane-kit-server-sdk/archive/220f63169e4bac79653937e97727406255279f7b.zip"
COPY products/website_server/src /app/website-src
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/website-src \
    CPK_WRAPPER_CONFIGURATION_FILE=/etc/cpk/website/control.json
USER node
EXPOSE 8080 8000
STOPSIGNAL SIGTERM
HEALTHCHECK NONE
ENTRYPOINT ["/opt/cpk-website/bin/python", "-m", "control_plane_kit_servers_website_server.process"]
CMD []
