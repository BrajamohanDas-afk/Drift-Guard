FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .
RUN pip install uv && uv sync --no-dev --frozen
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]