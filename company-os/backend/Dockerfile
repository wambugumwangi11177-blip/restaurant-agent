FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AGENT_DIRECTIVES_DIR=/srv/directives/agents
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /srv/backend/
COPY directives/ /srv/directives/
COPY execution/ /srv/execution/
RUN useradd --create-home app && chown -R app /srv
USER app
EXPOSE 8000
# Build from the company-os/ directory:  docker build -f backend/Dockerfile .
CMD ["sh", "-c", "gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-8000} --timeout 180"]
