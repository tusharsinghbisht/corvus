FROM node:22-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG CORVUS_API_URL=http://api:8000
ENV CORVUS_API_URL=$CORVUS_API_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 HOSTNAME=0.0.0.0 PORT=3000
RUN addgroup -S -g 10001 corvus && adduser -S -u 10001 -G corvus corvus
COPY --from=build --chown=corvus:corvus /app/.next/standalone ./
COPY --from=build --chown=corvus:corvus /app/.next/static ./.next/static
COPY --from=build --chown=corvus:corvus /app/public ./public
USER corvus
CMD ["node", "server.js"]
