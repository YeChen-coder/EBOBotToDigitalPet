FROM node:22-bookworm-slim AS core
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates git ripgrep && rm -rf /var/lib/apt/lists/*
COPY --chown=node:node src ./src
RUN mkdir -p /data /home/node/.codex && chown -R node:node /data /home/node/.codex
USER node
ENV NODE_ENV=production
CMD ["node", "src/watcher.mjs"]

FROM core AS worker
USER root
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
USER node
CMD ["node", "src/codex-worker.mjs"]
