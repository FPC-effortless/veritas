FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
COPY tests/ tests/
ENTRYPOINT ["iworld"]
"}},{
