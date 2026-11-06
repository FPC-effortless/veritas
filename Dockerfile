# syntax=docker/dockerfile:1
FROM cgr.dev/chainguard/wolfi-base@sha256:fd50bd0cdeb808cf4f45c9c9189e0cc7f7fcc27195d69abd6622c80527e7e021

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH \
    HOME=/home/veritas

WORKDIR /app

COPY pyproject.toml README.md LICENSE LICENSING.md ./
COPY src/ ./src/

RUN --mount=type=secret,id=proxy_ca,target=/etc/ssl/certs/ca-certificates.crt \
    export PIP_CERT=/etc/ssl/certs/ca-certificates.crt; \
    apk add --no-cache python-3.12=3.12.16-r3 py3.12-pip=26.2.2-r2 \
        libstdc++=16.2.0-r2 libgomp=16.2.0-r2 && \
    /usr/bin/python3.12 -m venv --without-pip /opt/venv && \
    /usr/bin/python3.12 -m pip --python /opt/venv/bin/python install . && \
    /usr/bin/python3.12 -m pip --python /opt/venv/bin/python check && \
    apk del py3.12-pip && \
    python -c 'import pathlib,shutil,sysconfig; shutil.rmtree(pathlib.Path(sysconfig.get_path("stdlib")) / "ensurepip")' && \
    addgroup -g 10001 veritas && \
    adduser -D -u 10001 -G veritas -h /home/veritas veritas

USER veritas

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()" || exit 1

CMD ["uvicorn", "investigation_world.tools.server:app", "--host", "0.0.0.0", "--port", "8000"]
