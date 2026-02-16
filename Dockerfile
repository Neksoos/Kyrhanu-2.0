# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY tsconfig.json ./
COPY src ./src
COPY sql ./sql
RUN npm run build

# ---- Runtime stage ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

COPY --from=build /app/dist ./dist
COPY --from=build /app/sql ./sql
COPY openapi.yaml ./openapi.yaml

EXPOSE 8080

# ✅ Міграції запускаються перед стартом сервера
CMD ["sh", "-c", "node dist/index.js"]