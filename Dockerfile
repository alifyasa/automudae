FROM python:3.12.3-slim AS builder

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml /app/
COPY poetry.lock /app/

RUN poetry update

COPY README.md /app/
COPY automudae /app/automudae

RUN poetry build

FROM python:3.12.3-slim AS runner

WORKDIR /app

COPY --from=builder /app/dist /app/dist

RUN pip install /app/dist/*.whl

CMD ["python", "-m", "automudae", "-f", "config/config.yaml"]
