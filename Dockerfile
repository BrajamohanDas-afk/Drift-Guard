FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY app/ ./app/

RUN pip install uv && uv sync --no-dev

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]