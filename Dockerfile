FROM python:3.12-slim

WORKDIR /workspace

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/workspace/app

COPY app/token_payments/ /workspace/app/token_payments/

CMD ["python", "-m", "token_payments", "health"]
