# One image, run as every swarm agent (AGENT_ID and ROLE come from docker/compose.yml).
# Standard library only: no pip installs, no model, no GPU.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY swarm.py agent.py payloads.json ./
# /shared is owned by the agent user so the named volume (inboxes, rogue flags) is writable
# by non-root agents: Docker copies this directory's ownership into a fresh volume.
RUN useradd --create-home --uid 10001 agent && mkdir -p /shared/inbox /shared/rogue && chown -R agent /shared
USER agent
CMD ["python", "agent.py"]
