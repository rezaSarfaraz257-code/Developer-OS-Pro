FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git curl ca-certificates build-essential util-linux && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/runner-venv && /opt/runner-venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/runner-venv/bin:${PATH}"
COPY main.py sandbox_exec.py ./
RUN mkdir -p /workspaces
# API remains root only to drop UID/GID for untrusted commands. Compose grants
# only the capabilities required for workspace ownership and privilege dropping;
# command processes lose the entire capability set.
USER root
EXPOSE 8080
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8080"]
