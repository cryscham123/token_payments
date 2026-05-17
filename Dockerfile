FROM python:3.12-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace/app

COPY app/token_payments/ /workspace/app/token_payments/
COPY Dockerfile .dockerignore docker-compose.yml .env.example /workspace/
COPY requirements-runtime.txt /workspace/requirements-runtime.txt
COPY app/postgres/init.d/001-token-payments-schema.sql /workspace/app/postgres/init.d/001-token-payments-schema.sql
COPY app/test_network/Dockerfile /workspace/app/test_network/Dockerfile

RUN python -m pip install --no-cache-dir -r /workspace/requirements-runtime.txt

CMD ["python", "-m", "token_payments", "health"]
