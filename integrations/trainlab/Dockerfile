# syntax=docker/dockerfile:1
FROM python:3.13-alpine@sha256:7984cf56ceaddebe4fefeb75d64000b9f45d8b77b11a09b24524da6cdc3af0c8
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="TrainLab" \
      org.opencontainers.image.source="https://github.com/FPC-effortless/veritas" \
      org.opencontainers.image.revision=$VCS_REF
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /opt/trainlab
COPY integrations/trainlab/pyproject.toml integrations/trainlab/README.md integrations/trainlab/requirements-server.txt integrations/trainlab/LICENSE ./
COPY integrations/trainlab/src ./src
COPY integrations/trainlab/examples ./examples
COPY integrations/forge/pyproject.toml /opt/forge/pyproject.toml
COPY integrations/forge/WORKBENCH.md /opt/forge/WORKBENCH.md
COPY integrations/forge/src /opt/forge/src
COPY integrations/forge/examples/dataset_quickstart.py /opt/forge/examples/dataset_quickstart.py
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    python -m pip install --no-cache-dir --require-hashes -r requirements-server.txt && \
    python -m pip install --no-cache-dir --no-deps . /opt/forge && \
    python -m pip uninstall -y pip && \
    rm -rf /usr/local/lib/python3.13/ensurepip && \
    chmod -R a+rX /opt/trainlab /opt/forge && \
    mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=3).read()"]
ENTRYPOINT ["trainlab"]
CMD ["serve", "--production", "--runs", "/data/runs", "--auth-file", "/run/secrets/trainlab-auth.json", "--forge-workspace", "/data/forge"]
