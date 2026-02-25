# ─────────────────────────────────────────────────────────────────
# Dockerfile.app — Self-contained Frontend + Backend
# ─────────────────────────────────────────────────────────────────

# ── Stage 1: Build the Next.js frontend ─────────────────────────
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --prefer-offline

COPY frontend/ ./

ARG NEXT_PUBLIC_API_URL=http://localhost:8001
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

# ── Stage 2: Python runtime ─────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install backend Python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy backend source
COPY backend/ /app/backend/
COPY locked_secrets/ /app/locked_secrets/
COPY api_key.txt* /app/
RUN mkdir -p /app/data

# Copy the Next.js standalone output
WORKDIR /app/frontend-standalone
COPY --from=frontend-build /app/frontend/.next/standalone ./
COPY --from=frontend-build /app/frontend/.next/static ./.next/static
COPY --from=frontend-build /app/frontend/public ./public

# Copy and set the entrypoint
WORKDIR /app
COPY docker/start-app.sh /app/start-app.sh
RUN chmod +x /app/start-app.sh

EXPOSE 3000 8001
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/app/start-app.sh"]
