FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY apps ./apps
COPY sql ./sql

RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "payment_platform.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
