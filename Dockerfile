FROM python:3.12.3-slim

RUN pip install --upgrade pip

WORKDIR /app

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY automudae/ ./automudae/

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "automudae", "-f", "config/config.yaml"]
