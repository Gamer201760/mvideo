FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG SITE_URL=""
ENV SITE_URL=$SITE_URL
RUN npm run build

FROM nginx:1.27-alpine
ENV API_UPSTREAM=http://backend:8000
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
