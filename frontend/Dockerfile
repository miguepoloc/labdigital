# syntax=docker/dockerfile:1
# ---- build: node 22 → dist/ (vue-tsc + vite-ssg) ----
FROM node:22-alpine AS build
WORKDIR /app
ENV CI=1
COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY . .
RUN npm run build

# ---- runtime: nginx sirviendo dist/ bajo /labdigital/ ----
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html/labdigital
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/healthz || exit 1
