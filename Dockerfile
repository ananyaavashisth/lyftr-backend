# --- Build stage ---
FROM python:3.11-slim AS build

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --upgrade pip && pip install --prefix=/install -r requirements.txt

# --- Runtime stage ---
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1

# Copy installed packages from build stage
COPY --from=build /install /usr/local
# Copy application code
COPY app ./app

EXPOSE 8000

# Default envs are overridden by docker-compose
ENV DATABASE_URL="sqlite:////data/app.db"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
