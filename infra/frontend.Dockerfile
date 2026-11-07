# Build context is ../frontend (see infra/docker-compose.yml).
# Runs the Vite dev server inside the container. A production static/nginx
# build is deferred to the deployment-polish phase (docs/implementation-plan.md
# Phase 9) — Phase 1 only needs a working dev loop.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]
