# Sentinel overseer: FastAPI (api.py) + the detection models, trained at build time.
# Build context: src/app/sentinel/_py (set in docker/compose.yml). Works with Docker and Podman.
#   docker compose -f docker/compose.yml up --build
# CPU only. No GPU, no LLM at inference.
FROM python:3.11-slim

# libgomp1 = the OpenMP runtime XGBoost links against. curl is for the healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# Deps first so code changes don't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Train both models into artifacts/ so score.py runs the real blend (components.fallback=false).
# Both read data/actions.csv (Noah's seeded dataset, committed).
RUN python model_anomaly.py && python model_supervised.py && ls -l artifacts/

# Run as a non-root user.
RUN useradd --create-home --uid 10001 sentinel && chown -R sentinel /app
USER sentinel

ENV SENTINEL_TICK_S=2
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
