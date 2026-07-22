# Build context is the repo root (see docker-compose.yml) because this
# service imports packages/contracts/src directly as TypeScript source.
FROM node:22-alpine

WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm install

WORKDIR /app
COPY apps/web ./apps/web
COPY packages/contracts ./packages/contracts

WORKDIR /app/apps/web
EXPOSE 3000
CMD ["npm", "run", "dev"]
