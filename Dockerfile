FROM python:3.12.3-slim

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml /app/
COPY poetry.lock /app/

RUN poetry update

COPY README.md /app/
COPY automudae /app/automudae

RUN poetry install

CMD ["poetry", "run", "python", "-m", "automudae"]
