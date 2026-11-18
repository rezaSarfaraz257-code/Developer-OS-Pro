FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv python3-pip git curl ca-certificates build-essential util-linux && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 runner
WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY main.py .
RUN mkdir -p /workspaces && chown -R runner:runner /workspaces /app
# API remains root only to drop UID/GID for untrusted commands. Compose grants
# only SETUID/SETGID; command processes lose the entire capability set.
USER root
EXPOSE 8080
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8080"]
