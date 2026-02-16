# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# ---- Runtime stage ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY --from=build /app/dist ./dist
COPY openapi.yaml ./openapi.yaml
COPY sql ./sql

EXPOSE 8080

# ✅ спочатку міграції (idempotent), потім сервер
CMD ["sh", "-c", "node dist/scripts/migrate.js && node dist/index.js"]