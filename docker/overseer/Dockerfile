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

# Train the models into artifacts/ so score.py runs the real blend (components.fallback=false).
# The behaviour models read data/actions.csv (committed). Prompt Guard trains on data/real/prompt_safety.parquet,
# which is NOT in git (no licence): run _py/fetch/fetch_all.py once before building, or it skips with a
# warning and prompt_risk stays 0. It never downloads during the build.
RUN python model_anomaly.py && python model_supervised.py && python prompt_guard.py && ls -l artifacts/

# Run as a non-root user.
RUN useradd --create-home --uid 10001 sentinel && chown -R sentinel /app
USER sentinel

ENV SENTINEL_TICK_S=2
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
