# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

# Dependencies (no lockfile in repo -> use npm install)
COPY package.json ./
RUN npm install --no-audit --no-fund

# Build TS -> dist
COPY tsconfig.json ./
COPY src ./src
COPY sql ./sql
COPY openapi.yaml ./openapi.yaml
RUN npm run build

# ---- Runtime stage ----
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=8080
# щоб не було подвійного запуску міграцій, якщо index.js теж вміє AUTO_MIGRATE
ENV AUTO_MIGRATE=false

# Install only prod deps
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

# App artifacts
COPY --from=build /app/dist ./dist
COPY --from=build /app/openapi.yaml ./openapi.yaml
COPY --from=build /app/sql ./sql

EXPOSE 8080

# 1) міграції (створять таблиці/ініт)
# 2) запуск API
CMD ["sh", "-c", "node dist/scripts/migrate.js && node dist/index.js"]