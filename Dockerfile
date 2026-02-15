# ---- Build stage ----
FROM node:20-alpine AS build
WORKDIR /app

# Dependencies (no lockfile in repo -> use npm install)
COPY package.json ./
RUN npm install --no-audit --no-fund

# Build TS -> dist
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

# ---- Runtime stage ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=8080

# Install only prod deps
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund

# App artifacts
COPY --from=build /app/dist ./dist
COPY openapi.yaml ./openapi.yaml
COPY sql ./sql

EXPOSE 8080
CMD ["node", "dist/index.js"]